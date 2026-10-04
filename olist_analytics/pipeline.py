from __future__ import annotations
import datetime as dt
import hashlib
import json
import re
import time
import uuid
from pathlib import Path
import duckdb
from .quality import check_analyses,check_models,check_staging,summarize_checks
from .reporting import data_profile,export_result,write_json
from .sources import load_raw

ROOT=Path(__file__).resolve().parents[1]

class PipelineError(RuntimeError):
    pass

def validate_config(config):
    required={"analysis_start","analysis_end","observation_end","min_state_orders","min_group_orders"}
    missing=required-set(config)
    if missing: raise PipelineError("Missing config keys: "+", ".join(sorted(missing)))
    try:
        start=dt.date.fromisoformat(str(config["analysis_start"]))
        end=dt.date.fromisoformat(str(config["analysis_end"]))
        observation=dt.datetime.fromisoformat(str(config["observation_end"]))
    except ValueError as error:
        raise PipelineError("Invalid analysis_start / analysis_end / observation_end") from error
    if start>end: raise PipelineError("analysis_start must not be after analysis_end")
    if observation.tzinfo is not None: raise PipelineError("observation_end requires source naive timestamps")
    if observation.date()<end: raise PipelineError("observation_end must cover analysis_end")
    thresholds={}
    for key in ["min_state_orders","min_group_orders"]:
        value=config[key]
        if isinstance(value,bool) or not isinstance(value,int) or value<=0:
            raise PipelineError(key+" must be a positive integer")
        thresholds[key]=value
    return dict(analysis_start=start.isoformat(),analysis_end=end.isoformat(),
                observation_end=observation.isoformat(sep=" "),**thresholds)

def load_current(output_dir: Path)->Path:
    try:
        pointer=json.loads((Path(output_dir)/"current.json").read_text(encoding="utf-8"))
        run_id=pointer["run_id"]
        if not isinstance(run_id,str) or not re.fullmatch(r"r[0-9a-f]{32}",run_id):
            raise ValueError("Invalid run id")
        path=Path(output_dir).resolve()/"runs"/run_id
        if not (path/"results.json").is_file(): raise ValueError("Missing results")
        return path
    except (OSError,ValueError,KeyError,TypeError) as error:
        raise PipelineError("Invalid current pointer or missing successful run") from error

def _ensure_quality(checks):
    quality=summarize_checks(checks)
    if quality["blocking_failures"]:
        names=[x["check"] for x in checks if x["severity"]=="error" and not x["passed"]]
        raise PipelineError("Blocking quality checks: "+", ".join(names))
    return quality

def run_pipeline(raw_dir: Path,output_dir: Path,config: dict)->dict:
    config=validate_config(config)
    raw_dir,output_dir=Path(raw_dir),Path(output_dir)
    run_id="r"+uuid.uuid4().hex
    run_dir=output_dir/"runs"/run_id
    run_dir.mkdir(parents=True);csv_dir=run_dir/"csv";csv_dir.mkdir()
    connection=duckdb.connect(str(run_dir/"warehouse.duckdb"))
    checks=[];timings={};start=time.perf_counter()
    try:
        manifest=load_raw(connection,raw_dir)
        write_json(run_dir/"source_manifest.json",manifest)
        fingerprint=hashlib.sha256(json.dumps(manifest["files"],sort_keys=True).encode()).hexdigest()
        connection.execute("CREATE TABLE analysis_config(analysis_start DATE,analysis_end DATE,"
                           "observation_end TIMESTAMP,min_state_orders INTEGER,min_group_orders INTEGER)")
        connection.execute("INSERT INTO analysis_config VALUES(?,?,?,?,?)",
                           [config[x] for x in ["analysis_start","analysis_end","observation_end",
                                               "min_state_orders","min_group_orders"]])
        staging=sorted((ROOT/"sql"/"staging").glob("*.sql"))
        if not staging: raise PipelineError("SQL staging implementation missing")
        for path in staging: connection.execute(path.read_text(encoding="utf-8"))
        checks.extend(check_staging(connection))
        write_json(run_dir/"quality.json",summarize_checks(checks));_ensure_quality(checks)
        for path in sorted((ROOT/"sql"/"models").glob("*.sql")):
            connection.execute(path.read_text(encoding="utf-8"))
        checks.extend(check_models(connection))
        write_json(run_dir/"quality.json",summarize_checks(checks))
        quality=_ensure_quality(checks)
        write_json(run_dir/"data_profile.json",data_profile(connection))
        exports={}
        for table in ["fact_orders","fact_order_items","dim_date","dim_customer_state","dim_category"]:
            meta=export_result(connection,"SELECT * FROM "+table+" ORDER BY ALL",csv_dir/(table+".csv"))
            exports[table]={key:value for key,value in meta.items() if key!="records"}
        queries=sorted((ROOT/"sql"/"analysis").glob("q*.sql"))
        if len(queries)!=10: raise PipelineError("Expected exactly 10 analysis SQL files; found "+str(len(queries)))
        analyses={}
        for path in queries:
            tick=time.perf_counter()
            analyses[path.stem]=export_result(connection,path.read_text(encoding="utf-8"),csv_dir/(path.stem+".csv"))
            timings[path.stem]=round(time.perf_counter()-tick,6)
        checks.extend(check_analyses(connection,analyses))
        write_json(run_dir/"quality.json",summarize_checks(checks))
        quality=_ensure_quality(checks)
        connection.execute("CHECKPOINT")
        results={"status":"passed","config":config,"source_fingerprint":fingerprint,"quality":quality,
                 "exports":exports,"analyses":analyses,"runtime":{"python":__import__("sys").version.split()[0],
                 "duckdb":duckdb.__version__,"elapsed_seconds":round(time.perf_counter()-start,6),
                 "sql_seconds":timings}}
        write_json(run_dir/"results.json",results);connection.close()
        pointer={"run_id":run_id,"status":"passed","source_fingerprint":fingerprint,"config":config}
        candidate=output_dir/("current."+uuid.uuid4().hex+".tmp")
        write_json(candidate,pointer);candidate.replace(output_dir/"current.json")
        return results
    except Exception as error:
        connection.close()
        write_json(run_dir/"quality.json",summarize_checks(checks))
        write_json(run_dir/"failed.json",{"status":"failed","error_type":type(error).__name__,
                   "message":str(error),"config":config,"quality":summarize_checks(checks)})
        if isinstance(error,PipelineError): raise
        raise PipelineError(str(error)) from error

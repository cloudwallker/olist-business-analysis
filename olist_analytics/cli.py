import argparse
import json
import sys
from pathlib import Path
import yaml
from .pipeline import PipelineError,ROOT,run_pipeline

def main(argv=None):
    parser=argparse.ArgumentParser(description="Rebuild Olist analysis from seven original CSVs.")
    parser.add_argument("--raw-dir",type=Path,default=ROOT/"data"/"raw")
    parser.add_argument("--output-dir",type=Path,default=ROOT/"build")
    parser.add_argument("--config",type=Path,default=ROOT/"config"/"analysis.example.yaml")
    args=parser.parse_args(argv)
    try:
        config=yaml.safe_load(args.config.read_text(encoding="utf-8"))
        if not isinstance(config,dict): raise PipelineError("Config must be a mapping")
        result=run_pipeline(args.raw_dir,args.output_dir,config)
    except (PipelineError,OSError,yaml.YAMLError) as error:
        print("Analysis failed: "+str(error),file=sys.stderr);return 2
    print(json.dumps({"status":result["status"],"blocking_failures":result["quality"]["blocking_failures"],
                      "warnings":result["quality"]["warnings"],"queries":len(result["analyses"]),
                      "elapsed_seconds":result["runtime"]["elapsed_seconds"]}))
    return 0


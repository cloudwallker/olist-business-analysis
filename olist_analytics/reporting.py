import csv
import datetime as dt
import hashlib
import json
from decimal import Decimal
from pathlib import Path

def json_default(value):
    if isinstance(value, Decimal): return str(value)
    if isinstance(value, (dt.date,dt.datetime)): return value.isoformat()
    if isinstance(value,Path): return value.name
    raise TypeError(type(value).__name__)

def write_json(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=json_default,
                               allow_nan=False)+"\n",encoding="utf-8")

def export_result(connection,query,path):
    cursor = connection.execute(query)
    columns = [x[0] for x in cursor.description]
    rows = cursor.fetchall()
    with path.open("w",encoding="utf-8",newline="") as stream:
        writer=csv.writer(stream,lineterminator="\n");writer.writerow(columns);writer.writerows(rows)
    return {"rows":len(rows),"columns":columns,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "records":[dict(zip(columns,row)) for row in rows]}

def data_profile(c):
    profile={name:{"raw_rows":c.execute("SELECT COUNT(*) FROM raw_"+name).fetchone()[0],
                  "staged_rows":c.execute("SELECT COUNT(*) FROM stg_"+name).fetchone()[0]}
             for name in ["orders","items","payments","customers","products","reviews","category_translation"]}
    profile["purchase_months"]=[dict(zip(["month","status","orders","purchase_days"],row))
       for row in c.execute("SELECT DATE_TRUNC('month',order_purchase_timestamp)::DATE,order_status,"
                            "COUNT(*),COUNT(DISTINCT CAST(order_purchase_timestamp AS DATE)) "
                            "FROM stg_orders GROUP BY 1,2 ORDER BY 1,2").fetchall()]
    return profile


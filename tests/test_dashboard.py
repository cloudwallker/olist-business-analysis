"""Power BI exports must preserve business grain, privacy, and file-format contracts."""
import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name) / "run"
        self.csv_dir = self.run / "csv"
        self.csv_dir.mkdir(parents=True)
        self.out = Path(self.temp.name) / "dashboard"
        fields = ["order_id", "customer_unique_id", "customer_state", "order_status", "purchase_date", "merchandise_value", "delivery_days", "delivery_eligible", "is_late", "review_score", "review_eligible", "review_before_delivery"]
        rows = [
            ["a", "private-a", "SP", "delivered", "2017-02-01", "100.00", "2", "true", "false", "5", "true", "false"],
            ["b", "private-b", "RJ", "delivered", "2017-02-02", "200.00", "4", "true", "true", "1", "true", "false"],
            ["c", "private-c", "SP", "delivered", "2017-02-03", "50.00", "", "false", "", "2", "true", ""],
            ["d", "private-d", "SP", "canceled", "2017-02-04", "25.00", "", "false", "", "", "false", ""],
            ["e", "private-e", "SP", "delivered", "2017-02-05", "150.00", "10", "true", "false", "", "false", ""],
            ["x", "private-x", "SP", "delivered", "2018-08-01", "1000.00", "1", "true", "false", "5", "true", "false"],
        ]
        self.write("fact_orders", fields, rows)
        self.write("fact_order_items", ["order_id", "order_item_id", "product_id", "category", "customer_state", "order_status", "purchase_date", "price", "freight_value"], [
            ["a", 1, "private-product", "A", "SP", "delivered", "2017-02-01", "60.00", "5"],
            ["a", 2, "private-product", "B", "SP", "delivered", "2017-02-01", "40.00", "5"],
            ["b", 1, "private-product", "A", "RJ", "delivered", "2017-02-02", "200.00", "5"],
            ["c", 1, "private-product", "B", "SP", "delivered", "2017-02-03", "50.00", "5"],
            ["d", 1, "private-product", "A", "SP", "canceled", "2017-02-04", "25.00", "5"],
            ["e", 1, "private-product", "A", "SP", "delivered", "2017-02-05", "150.00", "5"],
            ["x", 1, "private-product", "A", "SP", "delivered", "2018-08-01", "1000.00", "5"],
        ])
        self.write("dim_date", ["date", "month_start", "year", "quarter", "month"], [[f"2017-02-0{i}", "2017-02-01", 2017, 1, 1] for i in range(1, 6)] + [["2018-08-01", "2018-08-01", 2018, 3, 8]])
        self.write("dim_customer_state", ["customer_state"], [["RJ"], ["SP"], ["UNKNOWN"]])
        self.write("dim_category", ["category"], [["A"], ["B"], ["UNKNOWN"]])
        self.success_results = {
            "status": "passed",
            "quality": {"status": "passed", "blocking_failures": 0},
            "config": {
                "analysis_start": "2017-02-01",
                "analysis_end": "2018-07-31",
                "observation_end": "2018-07-31 23:59:59",
            },
            "fixture": "synthetic",
        }
        self.results_path = self.run / "results.json"
        self.results_path.write_text(json.dumps(self.success_results), encoding="utf-8")

    def write(self, name, fields, rows):
        with (self.csv_dir / f"{name}.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(fields)
            writer.writerows(rows)

    def build(self):
        script = ROOT / "scripts" / "build_dashboard.py"
        self.assertTrue(script.is_file(), "Power BI generator has not been implemented")
        spec = importlib.util.spec_from_file_location("dashboard_builder", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.build_dashboard(self.run, self.out)

    def test_anonymous_exports_preserve_order_grain_and_window(self):
        self.build()
        with (self.out / "data" / "fact_orders.csv").open(encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            rows = list(reader)
            self.assertEqual(len(rows), 5)
            self.assertNotIn("customer_unique_id", reader.fieldnames)
            self.assertNotIn("order_id", reader.fieldnames)
            self.assertNotIn("review_comment_message", reader.fieldnames)
        self.assertEqual([r["delay_group"] for r in rows], ["准时", "延迟", "无有效日期", "无有效日期", "准时"])
        self.assertEqual(sum(float(r["merchandise_value"]) for r in rows if r["order_status"] == "delivered"), 500.0)

    def test_dynamic_reconciliation_handles_missing_dates_and_unequal_groups(self):
        self.build()
        checks = json.loads((self.out / "reconciliation" / "expected.json").read_text(encoding="utf-8"))
        all_metrics = checks["all"]
        self.assertEqual(all_metrics["delivered_orders"], 4)
        self.assertEqual(all_metrics["gmv"], 500.0)
        self.assertEqual(all_metrics["aov"], 125.0)
        self.assertEqual(all_metrics["all_orders"], 5)
        self.assertEqual(all_metrics["canceled_orders"], 1)
        self.assertAlmostEqual(all_metrics["cancel_rate"], 0.2)
        self.assertEqual(all_metrics["delivery_orders"], 3)
        self.assertEqual(all_metrics["late_orders"], 1)
        self.assertAlmostEqual(all_metrics["late_rate"], 1 / 3)
        self.assertEqual(all_metrics["review_orders"], 3)
        self.assertEqual(all_metrics["low_score_orders"], 2)
        self.assertAlmostEqual(all_metrics["low_score_rate"], 2 / 3)
        self.assertEqual(all_metrics["joint_orders"], 2)
        self.assertEqual(all_metrics["delivery_coverage"], 0.75)
        self.assertEqual(all_metrics["review_coverage"], 0.75)
        self.assertEqual(all_metrics["joint_coverage"], 0.5)
        self.assertEqual(all_metrics["p50_days"], 4.0)
        self.assertAlmostEqual(all_metrics["p90_days"], 8.8)
        self.assertEqual(checks["state_SP"]["gmv"], 300.0)
        self.assertEqual(checks["state_SP"]["late_rate"], 0.0)

    def test_star_model_cannot_propagate_category_to_order_metrics(self):
        self.build()
        model = json.loads((self.out / "Olist.SemanticModel" / "model.bim").read_text(encoding="utf-8"))["model"]
        rel = model["relationships"]
        self.assertEqual(len(rel), 5)
        self.assertTrue(all(r["crossFilteringBehavior"] == "oneDirection" for r in rel))
        self.assertTrue(all(r["fromCardinality"] == "many" and r["toCardinality"] == "one" for r in rel))
        self.assertEqual([(r["fromTable"], r["toTable"]) for r in rel if r["toTable"] == "dim_category"], [("fact_order_items", "dim_category")])
        self.assertFalse(any(r["fromTable"].startswith("fact_") and r["toTable"].startswith("fact_") for r in rel))
        parameter = next(e for e in model["expressions"] if e["name"] == "DataFolder")
        self.assertNotIn(str(self.out), str(parameter))
        for table in model["tables"]:
            for column in table["columns"]:
                self.assertNotIn(column["name"], ["customer_unique_id", "product_id", "order_id"])

    def test_duration_does_not_require_an_estimated_delivery_date(self):
        with (self.csv_dir / "fact_orders.csv").open(encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            fields, rows = reader.fieldnames, list(reader)
        rows[2]["delivery_days"] = "6"
        with (self.csv_dir / "fact_orders.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        self.build()
        metrics = json.loads((self.out / "reconciliation" / "expected.json").read_text(encoding="utf-8"))["all"]
        self.assertEqual(metrics["delivery_orders"], 3)
        self.assertIn("duration_orders", metrics)
        self.assertEqual(metrics["duration_orders"], 4)
        self.assertEqual(metrics["p50_days"], 5.0)
        self.assertAlmostEqual(metrics["p90_days"], 8.8)

    def test_pbir_files_validate_against_microsoft_schemas(self):
        self.build()
        import jsonschema
        from referencing import Registry, Resource
        store = {}
        for path in (ROOT / "dashboard" / "schemas").rglob("schema.json"):
            schema = json.loads(path.read_text(encoding="utf-8-sig"))
            store[schema["$id"]] = schema
        registry = Registry().with_resources((url, Resource.from_contents(schema)) for url, schema in store.items())
        count = 0
        for path in self.out.rglob("*"):
            if path.suffix not in [".json", ".pbip", ".pbir", ".pbism"]:
                continue
            document = json.loads(path.read_text(encoding="utf-8"))
            if "$schema" not in document:
                continue
            self.assertIn(document["$schema"], store, str(path))
            schema = store[document["$schema"]]
            jsonschema.Draft7Validator(schema, registry=registry).validate(document)
            count += 1
        self.assertGreater(count, 20)
        pages = json.loads((self.out / "Olist.Report" / "definition" / "pages" / "pages.json").read_text(encoding="utf-8"))
        self.assertEqual(pages["pageOrder"], ["commerce", "delivery"])
        version = json.loads((self.out / "Olist.Report" / "definition" / "version.json").read_text(encoding="utf-8"))
        self.assertEqual(version["version"], "2.0.0", "Use the current PBIR content format from Microsoft Desktop projects")

    def test_missing_input_fails_before_overwriting_valid_project(self):
        self.build()
        before = (self.out / "Olist.pbip").read_bytes()
        (self.csv_dir / "fact_orders.csv").unlink()
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.build()
        self.assertEqual((self.out / "Olist.pbip").read_bytes(), before)

    def test_rejected_runs_preserve_every_existing_output_file(self):
        self.build()
        before = {path.relative_to(self.out): path.read_bytes() for path in self.out.rglob("*") if path.is_file()}
        # Balanced new source amounts would overwrite the old report if the gate ran too late.
        for name, column in [("fact_orders", "merchandise_value"), ("fact_order_items", "price")]:
            path = self.csv_dir / (name + ".csv")
            with path.open(encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                fields, rows = reader.fieldnames, list(reader)
            rows[0][column] = str(float(rows[0][column]) + 10)
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
        cases = [
            ("missing_results", None, None),
            ("failed_status", ("status",), "failed"),
            ("failed_quality", ("quality", "status"), "failed"),
            ("blocking_failure", ("quality", "blocking_failures"), 1),
            ("missing_quality", ("quality",), None),
            ("start_mismatch", ("config", "analysis_start"), "2017-01-01"),
            ("end_mismatch", ("config", "analysis_end"), "2018-08-31"),
            ("observation_mismatch", ("config", "observation_end"), "2018-08-31 23:59:59"),
            ("failed_marker", None, None),
        ]
        marker = self.run / "failed.json"
        for name, keys, value in cases:
            with self.subTest(name=name):
                results = json.loads(json.dumps(self.success_results))
                if marker.exists():
                    marker.unlink()
                if keys:
                    target = results
                    for key in keys[:-1]:
                        target = target[key]
                    target[keys[-1]] = value
                self.results_path.write_text(json.dumps(results), encoding="utf-8")
                if name == "missing_results":
                    self.results_path.unlink()
                if name == "failed_marker":
                    marker.write_text("{}", encoding="utf-8")
                with self.assertRaises((ValueError, FileNotFoundError)):
                    self.build()
                after = {path.relative_to(self.out): path.read_bytes() for path in self.out.rglob("*") if path.is_file()}
                self.assertEqual(after, before)

    def test_missing_results_does_not_create_a_new_output_directory(self):
        self.results_path.unlink()
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.build()
        self.assertFalse(self.out.exists())

    def test_manifest_discloses_desktop_scope_exclusion(self):
        self.build()
        manifest = json.loads((self.out / "build-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["desktop_validation"], "not_performed_scope_excluded")
        self.assertEqual(set(manifest["desktop_scope_exclusions"]), {"refresh", "dax_reconciliation", "pbix", "pdf"})
        self.assertFalse((self.out / "reconciliation" / "desktop-verified.json").exists())

    def test_generated_sql_reconciliation_matches_hand_checked_order_fixture(self):
        self.build()
        sql_file = self.out / "reconciliation" / "all.sql"
        self.assertTrue(sql_file.is_file(), "A SQL counterpart is required for actual DAX reconciliation")
        import duckdb
        connection = duckdb.connect()
        self.addCleanup(connection.close)
        connection.execute("CREATE TABLE fact_orders AS SELECT * FROM read_csv_auto(?)", [str(self.out / "data" / "fact_orders.csv")])
        cursor = connection.execute(sql_file.read_text(encoding="utf-8"))
        result = dict(zip([field[0] for field in cursor.description], cursor.fetchone()))
        self.assertEqual(float(result["gmv"]), 500.0)
        self.assertEqual(result["delivered_orders"], 4)
        self.assertEqual(result["joint_orders"], 2)
        self.assertAlmostEqual(result["late_rate"], 1 / 3)
        self.assertAlmostEqual(result["low_score_rate"], 2 / 3)
        self.assertEqual(result["p50_days"], 4.0)

    def test_report_provenance_changes_with_source_hash_and_excludes_private_paths(self):
        source = {"files": [{"filename": "olist_orders_dataset.csv", "sha256": "a" * 64, "local_path": "C:/Users/private-person/data.csv"}]}
        manifest = self.run / "source_manifest.json"
        manifest.write_text(json.dumps(source), encoding="utf-8")
        self.build()
        first = json.loads((self.out / "build-manifest.json").read_text(encoding="utf-8"))
        self.assertIn("source_snapshot", first)
        source["files"][0]["sha256"] = "b" * 64
        manifest.write_text(json.dumps(source), encoding="utf-8")
        self.build()
        second = json.loads((self.out / "build-manifest.json").read_text(encoding="utf-8"))
        self.assertNotEqual(first["source_snapshot"], second["source_snapshot"])
        page = json.loads((self.out / "Olist.Report/definition/pages/commerce/page.json").read_text(encoding="utf-8"))
        self.assertIn({"name": "sourceSnapshot", "value": second["source_snapshot"]}, page["annotations"])
        self.assertNotIn("private-person", json.dumps(second))


if __name__ == "__main__":
    unittest.main()


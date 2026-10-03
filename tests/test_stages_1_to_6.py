"""HTTP and SQLite acceptance checks for the current pharmacy stages.

Run from the repository root with:
    python -m unittest discover -s tests -v

The suite starts an isolated Uvicorn process and uses a temporary SQLite file;
it never writes test records to the developer's pharmacy.db.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def sqlite_connection(path: Path):
    connection = sqlite3.connect(path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


class PharmacyAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="pharmacy-acceptance-")
        cls.temp_path = Path(cls.temp_dir.name)
        cls.database_path = cls.temp_path / "acceptance.sqlite3"
        cls.log_path = cls.temp_path / "uvicorn.log"
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        environment = os.environ.copy()
        environment.update(
            {
                "DATABASE_URL": f"sqlite:///{cls.database_path.as_posix()}",
                "ENVIRONMENT": "development",
                "COOKIE_SECURE": "false",
                "BUSINESS_TIMEZONE": "Africa/Cairo",
                "PYTHONPATH": str(ROOT)
                + os.pathsep
                + environment.get("PYTHONPATH", ""),
            }
        )
        cls.log_file = cls.log_path.open("w", encoding="utf-8")
        cls.server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(cls.port),
                "--log-level",
                "warning",
            ],
            cwd=ROOT,
            env=environment,
            stdout=cls.log_file,
            stderr=subprocess.STDOUT,
        )

        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if cls.server.poll() is not None:
                cls.log_file.flush()
                raise RuntimeError(
                    "Acceptance server exited during startup:\n"
                    + cls.log_path.read_text(encoding="utf-8")
                )
            try:
                with build_opener().open(cls.base_url + "/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except (OSError, URLError):
                time.sleep(0.2)
        else:
            cls.server.terminate()
            cls.server.wait(timeout=10)
            cls.log_file.flush()
            raise RuntimeError(
                "Acceptance server did not become healthy:\n"
                + cls.log_path.read_text(encoding="utf-8")
            )

    @classmethod
    def tearDownClass(cls) -> None:
        if getattr(cls, "server", None) is not None:
            if cls.server.poll() is None:
                cls.server.terminate()
                cls.server.wait(timeout=10)
        if getattr(cls, "log_file", None) is not None:
            cls.log_file.close()
        if getattr(cls, "temp_dir", None) is not None:
            cls.temp_dir.cleanup()

    @staticmethod
    def _client():
        return build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def _request(
        self,
        client,
        method: str,
        path: str,
        payload: dict | None = None,
    ) -> tuple[int, object, dict[str, str]]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        request = Request(
            self.base_url + path,
            data=body,
            headers=headers,
            method=method,
        )
        try:
            response = client.open(request, timeout=10)
        except HTTPError as exc:
            response = exc
        with response:
            raw = response.read()
            try:
                data = json.loads(raw.decode("utf-8")) if raw else None
            except (UnicodeDecodeError, json.JSONDecodeError):
                data = raw.decode("utf-8", errors="replace")
            headers = {name.lower(): value for name, value in response.headers.items()}
            return response.status, data, headers

    def _signup(self, client, email: str, pharmacy_name: str) -> dict:
        status_code, body, _ = self._request(
            client,
            "POST",
            "/auth/signup",
            {
                "pharmacy_name": pharmacy_name,
                "full_name": "Pharmacy Owner",
                "email": email,
                "password": "Secure-Pharmacy-Password-2026",
            },
        )
        self.assertEqual(status_code, 201, body)
        return body

    def test_stages_one_through_six_and_transactional_fefo_sales(self) -> None:
        anonymous = self._client()
        status_code, page, _ = self._request(anonymous, "GET", "/")
        self.assertEqual(status_code, 200)
        self.assertIn("Pharmacy", page)

        status_code, health, _ = self._request(anonymous, "GET", "/health")
        self.assertEqual(status_code, 200)
        self.assertEqual(health["status"], "ok")

        status_code, docs, docs_headers = self._request(anonymous, "GET", "/docs")
        self.assertEqual(status_code, 200)
        self.assertIn("swagger-ui", docs.lower())
        self.assertIn("cdn.jsdelivr.net", docs_headers.get("content-security-policy", ""))

        status_code, openapi, _ = self._request(anonymous, "GET", "/openapi.json")
        self.assertEqual(status_code, 200)
        self.assertIn("/api/v1/products/", openapi["paths"])
        self.assertIn("/api/v1/inventory/{batch_id}", openapi["paths"])
        self.assertIn("/api/v1/inventory/product/{product_id}/stock", openapi["paths"])
        self.assertIn("/api/v1/sales/", openapi["paths"])

        first_pharmacy = self._client()
        second_pharmacy = self._client()
        owner = self._signup(first_pharmacy, "owner@example.com", "Nile Pharmacy")
        duplicate_status, _, _ = self._request(
            anonymous,
            "POST",
            "/auth/signup",
            {
                "pharmacy_name": "Duplicate",
                "full_name": "Duplicate User",
                "email": " OWNER@example.com ",
                "password": "Secure-Pharmacy-Password-2026",
            },
        )
        self.assertEqual(duplicate_status, 409)
        second_owner = self._signup(
            second_pharmacy,
            "other-owner@example.com",
            "Delta Pharmacy",
        )

        status_code, unauthorized, _ = self._request(
            anonymous,
            "GET",
            "/api/v1/products/",
        )
        self.assertEqual(status_code, 401, unauthorized)

        status_code, current_user, _ = self._request(first_pharmacy, "GET", "/auth/me")
        self.assertEqual(status_code, 200)
        self.assertEqual(current_user["pharmacy_id"], owner["pharmacy_id"])

        def create_product(client, name: str, barcode: str, price: str, description: str | None = None):
            return self._request(
                client,
                "POST",
                "/api/v1/products/",
                {
                    "name": name,
                    "barcode": barcode,
                    "selling_price": price,
                    "description": description,
                },
            )

        status_code, _, _ = create_product(
            first_pharmacy,
            "Invalid Price",
            "BAD-PRICE",
            "-1.00",
        )
        self.assertEqual(status_code, 422)

        status_code, panadol, _ = create_product(
            first_pharmacy,
            "Panadol Extra",
            "PAN-001",
            "120.00",
            "Pain relief tablets",
        )
        self.assertEqual(status_code, 201, panadol)
        panadol_id = panadol["id"]
        self.assertEqual(panadol["description"], "Pain relief tablets")

        status_code, duplicate_product, _ = create_product(
            first_pharmacy,
            "Duplicate Barcode",
            "PAN-001",
            "10.00",
        )
        self.assertEqual(status_code, 409, duplicate_product)

        status_code, fetched_product, _ = self._request(
            first_pharmacy,
            "GET",
            f"/api/v1/products/{panadol_id}",
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(fetched_product["name"], "Panadol Extra")

        status_code, replaced_product, _ = self._request(
            first_pharmacy,
            "PUT",
            f"/api/v1/products/{panadol_id}",
            {
                "name": "Panadol Extra",
                "barcode": "PAN-001",
                "description": "Pain relief tablets",
                "selling_price": "120.00",
            },
        )
        self.assertEqual(status_code, 200, replaced_product)

        status_code, patched_product, _ = self._request(
            first_pharmacy,
            "PATCH",
            f"/api/v1/products/{panadol_id}",
            {"description": "Retail pack"},
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(patched_product["description"], "Retail pack")

        status_code, missing_product, _ = self._request(
            first_pharmacy,
            "GET",
            "/api/v1/products/999999",
        )
        self.assertEqual(status_code, 404, missing_product)

        status_code, other_tenant_product, _ = self._request(
            second_pharmacy,
            "GET",
            f"/api/v1/products/{panadol_id}",
        )
        self.assertEqual(status_code, 404, other_tenant_product)
        status_code, same_barcode_other_tenant, _ = create_product(
            second_pharmacy,
            "Panadol in Other Pharmacy",
            "PAN-001",
            "130.00",
        )
        self.assertEqual(status_code, 201, same_barcode_other_tenant)
        self.assertNotEqual(owner["pharmacy_id"], second_owner["pharmacy_id"])

        status_code, _, _ = create_product(
            first_pharmacy,
            "Amoxicillin",
            "AMX-001",
            "55.00",
        )
        self.assertEqual(status_code, 201)
        products_status, products, _ = self._request(
            first_pharmacy,
            "GET",
            "/api/v1/products/?limit=500",
        )
        self.assertEqual(products_status, 200)
        amoxicillin = next(product for product in products if product["name"] == "Amoxicillin")
        amoxicillin_id = amoxicillin["id"]

        today_date = datetime.now(ZoneInfo("Africa/Cairo")).date()
        today = today_date.isoformat()
        expiry_a = date(today_date.year + 1, 1, 15).isoformat()
        expiry_b = date(today_date.year + 1, 8, 20).isoformat()
        expiry_crud = date(today_date.year + 1, 5, 1).isoformat()
        expiry_amoxicillin = date(today_date.year + 1, 6, 1).isoformat()
        past_date = "2000-01-01"
        status_code, invalid_batch, _ = self._request(
            first_pharmacy,
            "POST",
            "/api/v1/inventory/",
            {
                "product_id": panadol_id,
                "batch_number": "EXPIRED",
                "quantity": 10,
                "unit_cost": "80.00",
                "expiry_date": past_date,
            },
        )
        self.assertEqual(status_code, 422, invalid_batch)

        status_code, invalid_quantity, _ = self._request(
            first_pharmacy,
            "POST",
            "/api/v1/inventory/",
            {
                "product_id": panadol_id,
                "batch_number": "ZERO",
                "quantity": -1,
                "unit_cost": "80.00",
                "expiry_date": expiry_a,
            },
        )
        self.assertEqual(status_code, 422, invalid_quantity)

        status_code, invalid_cost, _ = self._request(
            first_pharmacy,
            "POST",
            "/api/v1/inventory/",
            {
                "product_id": panadol_id,
                "batch_number": "BAD-COST",
                "quantity": 1,
                "unit_cost": "-1.00",
                "expiry_date": expiry_a,
            },
        )
        self.assertEqual(status_code, 422, invalid_cost)

        status_code, missing_batch_product, _ = self._request(
            first_pharmacy,
            "POST",
            "/api/v1/inventory/",
            {
                "product_id": 999999,
                "batch_number": "NO-PRODUCT",
                "quantity": 1,
                "unit_cost": "1.00",
                "expiry_date": expiry_a,
            },
        )
        self.assertEqual(status_code, 404, missing_batch_product)

        def receive_batch(
            product_id: int,
            number: str,
            quantity: int,
            expiry: str,
            cost: str = "80.00",
            path: str = "/api/v1/inventory/",
        ):
            return self._request(
                first_pharmacy,
                "POST",
                path,
                {
                    "product_id": product_id,
                    "batch_number": number,
                    "quantity": quantity,
                    "unit_cost": cost,
                    "expiry_date": expiry,
                },
            )

        status_code, batch_a, _ = receive_batch(panadol_id, "PAN-A", 100, expiry_a)
        self.assertEqual(status_code, 201, batch_a)
        status_code, batch_b, _ = receive_batch(panadol_id, "PAN-B", 50, expiry_b, "85.00")
        self.assertEqual(status_code, 201, batch_b)
        batch_a_id = batch_a["id"]
        batch_b_id = batch_b["id"]

        status_code, fetched_batch, _ = self._request(
            first_pharmacy,
            "GET",
            f"/api/v1/inventory/{batch_a_id}",
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(fetched_batch["quantity"], 100)
        status_code, batches, _ = self._request(first_pharmacy, "GET", "/api/v1/inventory/")
        self.assertEqual(status_code, 200)
        self.assertEqual(len(batches), 2)
        status_code, legacy_batches, _ = self._request(
            first_pharmacy,
            "GET",
            "/api/v1/inventory/batches/",
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(len(legacy_batches), 2)

        status_code, stock, _ = self._request(
            first_pharmacy,
            "GET",
            f"/api/v1/inventory/product/{panadol_id}/stock",
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(stock["on_hand_quantity"], 150)
        self.assertEqual(stock["sellable_quantity"], 150)
        status_code, legacy_stock, _ = self._request(
            first_pharmacy,
            "GET",
            f"/api/v1/inventory/stock/{panadol_id}",
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(legacy_stock["sellable_quantity"], 150)

        status_code, crud_product, _ = create_product(
            first_pharmacy,
            "Gauze Roll",
            "GAUZE-001",
            "12.00",
        )
        self.assertEqual(status_code, 201)
        status_code, crud_batch, _ = receive_batch(
            crud_product["id"],
            "GAUZE-A",
            5,
            expiry_crud,
            "4.00",
            "/api/v1/inventory/batches/",
        )
        self.assertEqual(status_code, 201)
        status_code, updated_batch, _ = self._request(
            first_pharmacy,
            "PUT",
            f"/api/v1/inventory/{crud_batch['id']}",
            {
                "batch_number": "GAUZE-A-CORRECTED",
                "quantity": 0,
                "unit_cost": "4.25",
                "expiry_date": expiry_crud,
            },
        )
        self.assertEqual(status_code, 200, updated_batch)
        self.assertEqual(updated_batch["quantity"], 0)

        status_code, positive_batch_delete, _ = self._request(
            first_pharmacy,
            "DELETE",
            f"/api/v1/inventory/{batch_a_id}",
        )
        self.assertEqual(status_code, 409, positive_batch_delete)
        status_code, _, _ = self._request(
            first_pharmacy,
            "DELETE",
            f"/api/v1/inventory/{crud_batch['id']}",
        )
        self.assertEqual(status_code, 204)
        status_code, missing_batch, _ = self._request(
            first_pharmacy,
            "GET",
            f"/api/v1/inventory/{crud_batch['id']}",
        )
        self.assertEqual(status_code, 404, missing_batch)

        status_code, sale_20, _ = self._request(
            first_pharmacy,
            "POST",
            "/api/v1/sales/",
            {
                "items": [
                    {
                        "product_id": panadol_id,
                        "quantity": 20,
                        "unit_price": "0.01",
                    }
                ]
            },
        )
        self.assertEqual(status_code, 201, sale_20)
        self.assertEqual(float(sale_20["total_amount"]), 2400.0)
        self.assertEqual(
            [(item["batch_number"], item["quantity"]) for item in sale_20["items"][0]["batch_allocations"]],
            [("PAN-A", 20)],
        )

        status_code, sale_90, _ = self._request(
            first_pharmacy,
            "POST",
            "/api/v1/sales/",
            {"items": [{"product_id": panadol_id, "quantity": 90}]},
        )
        self.assertEqual(status_code, 201, sale_90)
        self.assertEqual(float(sale_90["total_amount"]), 10800.0)
        self.assertEqual(
            [(item["batch_number"], item["quantity"]) for item in sale_90["items"][0]["batch_allocations"]],
            [("PAN-A", 80), ("PAN-B", 10)],
        )

        status_code, stock_after_examples, _ = self._request(
            first_pharmacy,
            "GET",
            f"/api/v1/inventory/product/{panadol_id}/stock",
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(stock_after_examples["on_hand_quantity"], 40)
        self.assertEqual(stock_after_examples["sellable_quantity"], 40)

        status_code, amoxicillin_batch, _ = receive_batch(
            amoxicillin_id,
            "AMX-A",
            10,
            expiry_amoxicillin,
            "20.00",
        )
        self.assertEqual(status_code, 201)
        status_code, multi_product_sale, _ = self._request(
            first_pharmacy,
            "POST",
            "/api/v1/sales/",
            {
                "items": [
                    {"product_id": panadol_id, "quantity": 1},
                    {"product_id": amoxicillin_id, "quantity": 2},
                ]
            },
        )
        self.assertEqual(status_code, 201, multi_product_sale)
        self.assertEqual(float(multi_product_sale["total_amount"]), 230.0)
        self.assertEqual(len(multi_product_sale["items"]), 2)

        status_code, bad_quantity, _ = self._request(
            first_pharmacy,
            "POST",
            "/api/v1/sales/",
            {"items": [{"product_id": panadol_id, "quantity": 0}]},
        )
        self.assertEqual(status_code, 422, bad_quantity)
        status_code, duplicate_sale_lines, _ = self._request(
            first_pharmacy,
            "POST",
            "/api/v1/sales/",
            {
                "items": [
                    {"product_id": panadol_id, "quantity": 1},
                    {"product_id": panadol_id, "quantity": 1},
                ]
            },
        )
        self.assertEqual(status_code, 422, duplicate_sale_lines)
        status_code, missing_sale_product, _ = self._request(
            first_pharmacy,
            "POST",
            "/api/v1/sales/",
            {"items": [{"product_id": 999999, "quantity": 1}]},
        )
        self.assertEqual(status_code, 404, missing_sale_product)
        status_code, insufficient_stock, _ = self._request(
            first_pharmacy,
            "POST",
            "/api/v1/sales/",
            {"items": [{"product_id": panadol_id, "quantity": 50}]},
        )
        self.assertEqual(status_code, 409, insufficient_stock)
        status_code, stock_after_rejections, _ = self._request(
            first_pharmacy,
            "GET",
            f"/api/v1/inventory/product/{panadol_id}/stock",
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(stock_after_rejections["sellable_quantity"], 39)
        status_code, sales_after_rejections, _ = self._request(
            first_pharmacy,
            "GET",
            "/api/v1/sales/",
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(len(sales_after_rejections), 3)

        # Insert historical expired stock directly to verify it is reported but never sold.
        with sqlite_connection(self.database_path) as connection:
            tenant_id = connection.execute(
                "SELECT tenant_id FROM products WHERE id = ?",
                (panadol_id,),
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO inventory_batches
                   (product_id, tenant_id, batch_number, quantity, unit_cost, received_on, expiry_date, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    panadol_id,
                    tenant_id,
                    "PAN-EXPIRED",
                    5,
                    "70.00",
                    today,
                    past_date,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

        status_code, stock_with_expired, _ = self._request(
            first_pharmacy,
            "GET",
            f"/api/v1/inventory/product/{panadol_id}/stock",
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(stock_with_expired["on_hand_quantity"], 44)
        self.assertEqual(stock_with_expired["expired_quantity"], 5)
        self.assertEqual(stock_with_expired["sellable_quantity"], 39)

        with sqlite_connection(self.database_path) as connection:
            sales_before_failure = connection.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
            quantity_before_failure = connection.execute(
                "SELECT quantity FROM inventory_batches WHERE id = ?",
                (batch_b_id,),
            ).fetchone()[0]
            connection.execute(
                """CREATE TRIGGER fail_sale_allocation BEFORE INSERT ON sale_item_batches
                   BEGIN SELECT RAISE(ABORT, 'injected acceptance-test failure'); END"""
            )

        try:
            status_code, _, _ = self._request(
                first_pharmacy,
                "POST",
                "/api/v1/sales/",
                {"items": [{"product_id": panadol_id, "quantity": 1}]},
            )
            self.assertEqual(status_code, 500)
        finally:
            with sqlite_connection(self.database_path) as connection:
                connection.execute("DROP TRIGGER IF EXISTS fail_sale_allocation")

        with sqlite_connection(self.database_path) as connection:
            sales_after_failure = connection.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
            quantity_after_failure = connection.execute(
                "SELECT quantity FROM inventory_batches WHERE id = ?",
                (batch_b_id,),
            ).fetchone()[0]
            self.assertEqual(sales_after_failure, sales_before_failure)
            self.assertEqual(quantity_after_failure, quantity_before_failure)

            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            expected_tables = {
                "products",
                "inventory_batches",
                "suppliers",
                "purchases",
                "purchase_items",
                "sales",
                "sale_items",
                "sale_item_batches",
            }
            self.assertTrue(expected_tables.issubset(tables))
            self.assertIn(
                "description",
                {row[1] for row in connection.execute("PRAGMA table_info(products)")},
            )
            connection.execute("PRAGMA foreign_keys=ON")
            self.assertTrue(connection.execute("PRAGMA foreign_key_list(inventory_batches)").fetchall())
            expected_foreign_tables = {
                "inventory_batches": {"products", "purchase_items", "pharmacies"},
                "purchases": {"suppliers", "pharmacies"},
                "purchase_items": {"purchases", "products", "pharmacies"},
                "sales": {"pharmacies"},
                "sale_items": {"sales", "products", "pharmacies"},
                "sale_item_batches": {"sale_items", "inventory_batches", "pharmacies"},
            }
            for table, expected in expected_foreign_tables.items():
                actual = {
                    row[2]
                    for row in connection.execute(f'PRAGMA foreign_key_list("{table}")')
                }
                self.assertTrue(expected.issubset(actual), (table, actual))
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])

            persisted = connection.execute(
                """SELECT si.quantity, si.unit_price, sib.batch_number, sib.quantity
                   FROM sale_items AS si
                   JOIN sale_item_batches AS sib ON sib.sale_item_id = si.id
                   WHERE si.sale_id = ?
                   ORDER BY sib.id""",
                (sale_90["id"],),
            ).fetchall()
            self.assertEqual(
                persisted,
                [(90, 120, "PAN-A", 80), (90, 120, "PAN-B", 10)],
            )

        status_code, archived_product, _ = self._request(
            first_pharmacy,
            "POST",
            "/api/v1/products/",
            {
                "name": "Archive Test",
                "barcode": "ARCHIVE-001",
                "selling_price": "1.00",
            },
        )
        self.assertEqual(status_code, 201, archived_product)
        status_code, _, _ = self._request(
            first_pharmacy,
            "DELETE",
            f"/api/v1/products/{archived_product['id']}",
        )
        self.assertEqual(status_code, 204)
        status_code, archived_read, _ = self._request(
            first_pharmacy,
            "GET",
            f"/api/v1/products/{archived_product['id']}",
        )
        self.assertEqual(status_code, 200)
        self.assertFalse(archived_read["is_active"])


if __name__ == "__main__":
    unittest.main()

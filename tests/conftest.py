import pytest

from queryops.models import Catalog
from queryops.retrieval import HybridRetriever


@pytest.fixture
def catalog():
    return Catalog.from_dict({
        "objects": [
            {"name": "orders", "schema": "sales", "description": "Order revenue and date", "grain": "one row per order",
             "columns": [{"name": "customer_id", "data_type": "int", "nullable": False},
                         {"name": "revenue", "data_type": "decimal", "nullable": False},
                         {"name": "order_date", "data_type": "date", "nullable": False}]},
            {"name": "customers", "schema": "sales", "description": "Customer and region lookup",
             "columns": [{"name": "customer_id", "data_type": "int", "nullable": False},
                         {"name": "region", "data_type": "text", "nullable": False}]},
            {"name": "products", "schema": "sales", "description": "Product catalog",
             "columns": [{"name": "product_id", "data_type": "int"}]}
        ],
        "relationships": [{"left_object": "orders", "left_column": "customer_id", "right_object": "customers", "right_column": "customer_id"}],
        "lineage": [{"upstream": "orders", "downstream": "monthly_orders", "summary": "Monthly aggregate"}]
    })


@pytest.fixture
def retriever(catalog):
    return HybridRetriever(catalog)

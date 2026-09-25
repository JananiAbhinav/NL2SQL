import pytest

from queryops.sql_agent import SQLAgent, SQLSafetyError, validate_read_only_sql


@pytest.mark.parametrize("sql", ["SELECT * FROM orders", "WITH x AS (SELECT 1) SELECT * FROM x;\n"])
def test_read_queries_are_allowed(sql):
    assert validate_read_only_sql(sql).upper().startswith(("SELECT", "WITH"))


@pytest.mark.parametrize("sql", ["DELETE FROM orders", "SELECT 1; DROP TABLE orders", "SELECT * FROM x -- hi", "SELECT update FROM x"])
def test_unsafe_sql_is_rejected(sql):
    with pytest.raises(SQLSafetyError):
        validate_read_only_sql(sql)


class Generator:
    def __init__(self): self.errors = []
    def generate(self, question, context, dialect, previous_sql="", error=""):
        self.errors.append(error)
        return "SELECT revenue FROM sales.orders"


class BrokenExecutor:
    def __init__(self, message): self.message, self.calls = message, 0
    def execute(self, sql):
        self.calls += 1
        raise RuntimeError(self.message)


def test_authorization_failure_is_not_retried(catalog, retriever):
    generator, executor = Generator(), BrokenExecutor("Permission denied")
    answer = SQLAgent(catalog, retriever, generator, executor).answer("order revenue")
    assert answer.attempts == 1
    assert executor.calls == 1


def test_execution_error_is_retried_at_most_three_times(catalog, retriever):
    generator, executor = Generator(), BrokenExecutor("unknown column")
    answer = SQLAgent(catalog, retriever, generator, executor).answer("order revenue")
    assert answer.attempts == 4
    assert executor.calls == 4

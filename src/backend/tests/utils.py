from ctf_proxy.db.models import ProxyStatsDB


def assert_table(db: ProxyStatsDB, table: str, *, expect: list[dict]):
    columns = set()
    for row in expect:
        columns.update(row.keys())
    if not columns:
        columns = {"1"}
    columns_list = sorted(columns)
    with db.connect() as conn:
        tx = conn.cursor()
        cols_str = ", ".join(columns_list)
        tx.execute(f"SELECT {cols_str} FROM {table} ORDER BY id")
        rows = tx.fetchall()

        assert len(rows) == len(expect), (
            f"Expected {len(expect)} rows in `{table}`, got {len(rows)}"
        )
        for i, row in enumerate(rows):
            expected_row = expect[i]
            actual_row = dict(zip(columns_list, row, strict=False))
            for k, v in expected_row.items():
                assert actual_row[k] == v, (
                    f"Row {i} column '{k}': expected {v}, got {actual_row[k]}"
                )

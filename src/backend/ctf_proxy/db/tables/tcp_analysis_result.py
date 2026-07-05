from ctf_proxy.db.tables.analysis_result import AnalysisResultTable


class TcpAnalysisResultTable(AnalysisResultTable):
    table = "tcp_analysis_result"
    ref_column = "tcp_connection_id"
    source = "tcp"

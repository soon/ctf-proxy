from ctf_proxy.db.tables.analysis_result import AnalysisResultTable


class HttpAnalysisResultTable(AnalysisResultTable):
    table = "http_analysis_result"
    ref_column = "http_request_id"
    source = "http"

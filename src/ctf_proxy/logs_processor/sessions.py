from bisect import bisect_left, bisect_right, insort
from collections import defaultdict
from http.cookies import SimpleCookie
from typing import NamedTuple

from ctf_proxy.config.config import Config

__all__ = ["SessionsStorage"]

RequestID = int
Port = int
Timestamp = int
Headers = list[tuple[str, str]]
Session = str


class RequestInfo(NamedTuple):
    start_time: Timestamp
    session_in: Session | None
    session_out: Session | None


class Link(NamedTuple):
    from_request_id: RequestID
    to_request_id: RequestID


class SessionRequests:
    def __init__(self) -> None:
        self.requests: list[tuple[Timestamp, RequestID]] = []

    def add_request(self, timestamp: Timestamp, request_id: RequestID) -> None:
        insort(self.requests, (timestamp, request_id))

    def find_request_before(self, timestamp: Timestamp) -> RequestID | None:
        index = bisect_left(self.requests, (timestamp, 0))
        if index > 0:
            return self.requests[index - 1][1]
        return None

    def find_request_after(self, timestamp: Timestamp) -> RequestID | None:
        index = bisect_right(self.requests, (timestamp, float("inf")))
        if index < len(self.requests):
            return self.requests[index][1]
        return None


class SessionsStorage:
    def __init__(self, config: Config) -> None:
        self.requests: dict[tuple[Port, RequestID], RequestInfo] = defaultdict()
        self.request_sessions: dict[tuple[Port, Session], SessionRequests] = defaultdict(
            SessionRequests
        )
        self.response_sessions: dict[tuple[Port, Session], SessionRequests] = defaultdict(
            SessionRequests
        )
        self.config = config

    def get_in_session(self, headers: Headers, port: Port) -> Session | None:
        cookie_headers = [value for key, value in headers if key == "cookie"]
        if not cookie_headers:
            return None

        service = self.config.get_service_by_port(port)
        cookie_names = (
            service.session_cookie_names
            if service
            else [
                "session",
                "sessid",
                "sid",
                "token",
                "auth",
                "sessionid",
                ".AspNetCore.Identity.Application",
            ]
        )

        for cookie_value in cookie_headers:
            cookie = SimpleCookie()
            cookie.load(cookie_value)

            for cookie_name in cookie_names:
                if cookie_name in cookie:
                    return cookie[cookie_name].value

        return None

    def get_out_session(self, headers: Headers, port: Port) -> Session | None:
        set_cookie_headers = [value for key, value in headers if key == "set-cookie"]
        if not set_cookie_headers:
            return None

        service = self.config.get_service_by_port(port)
        cookie_names = (
            service.session_cookie_names
            if service
            else [
                "session",
                "sessid",
                "sid",
                "token",
                "auth",
                "sessionid",
                ".AspNetCore.Identity.Application",
            ]
        )

        for cookie_value in set_cookie_headers:
            cookie = SimpleCookie()
            cookie.load(cookie_value)

            for cookie_name in cookie_names:
                if cookie_name in cookie:
                    return cookie[cookie_name].value

        return None

    def add_request(
        self,
        port: Port,
        request_id: RequestID,
        start_time: Timestamp,
        request_headers: Headers,
        response_headers: Headers,
    ) -> None:
        in_session = self.get_in_session(request_headers, port)
        out_session = self.get_out_session(response_headers, port)

        if in_session or out_session:
            self.requests[(port, request_id)] = RequestInfo(start_time, in_session, out_session)

        if in_session:
            self.request_sessions[(port, in_session)].add_request(start_time, request_id)
        if out_session:
            self.response_sessions[(port, out_session)].add_request(start_time, request_id)

    def get_links(self, port: Port, request_id: RequestID) -> list[Link]:
        links: list[Link] = []
        request_info = self.requests.get((port, request_id))
        if not request_info:
            return links

        in_session = request_info.session_in
        out_session = request_info.session_out

        if in_session:
            session_requests = self.request_sessions.get((port, in_session))
            if session_requests:
                linked_request_id = session_requests.find_request_before(request_info.start_time)
                if linked_request_id is not None:
                    links.append(Link(linked_request_id, request_id))

        if out_session:
            session_requests = self.response_sessions.get((port, out_session))
            if session_requests:
                linked_request_id = session_requests.find_request_after(request_info.start_time)
                if linked_request_id is not None:
                    links.append(Link(request_id, linked_request_id))

        return links

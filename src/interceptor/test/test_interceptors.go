package main

import (
	"strings"
)

func registerHttpInterceptors() {
	RegisterHttpInterceptor(15001, "/blocked path",
		MatchHttpRequest(Matcher{
			Path: MatchPrefix("/blocked"),
		}), DoHttpBlock)

	RegisterHttpInterceptor(15001, "/paused path",
		MatchHttpRequest(Matcher{
			Path: MatchPrefix("/paused"),
		}), DoHttpPause)

	RegisterHttpInterceptor(15001, "/modified path",
		MatchHttpRequest(Matcher{
			Path: MatchPrefix("/modified"),
		}), ModifyHttpResponseBody(func(body []byte) []byte {
			return []byte(strings.ToUpper(string(body)))
		}))

	RegisterHttpInterceptor(15001, "/replaced path",
		MatchHttpRequest(Matcher{
			Path: MatchPrefix("/replaced"),
		}), DoReplaceHttpResponseBody([]byte("new response body")))
}

func registerTcpInterceptors() {
}

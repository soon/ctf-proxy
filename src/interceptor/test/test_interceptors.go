package main

import (
	"strings"
)

func registerInterceptors() {
	RegisterInterceptor(15001, "/blocked path",
		MatchHttpRequest(Matcher{
			Path: MatchPrefix("/blocked"),
		}), DoBlock)

	RegisterInterceptor(15001, "/paused path",
		MatchHttpRequest(Matcher{
			Path: MatchPrefix("/paused"),
		}), DoPause)

	RegisterInterceptor(15001, "/modified path",
		MatchHttpRequest(Matcher{
			Path: MatchPrefix("/modified"),
		}), ModifyHttpResponseBody(func(body []byte) []byte {
			return []byte(strings.ToUpper(string(body)))
		}))

	RegisterInterceptor(15001, "/replaced path",
		MatchHttpRequest(Matcher{
			Path: MatchPrefix("/replaced"),
		}), DoReplaceHttpResponseBody([]byte("new response body")))
}

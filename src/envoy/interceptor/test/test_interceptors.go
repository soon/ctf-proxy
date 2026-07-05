package main

import (
	"strings"

	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
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
	RegisterTcpInterceptor(15002, "block on marker",
		func(w *TcpWhenContext) bool {
			if w.Stage != TcpStageDownstreamData {
				return false
			}
			data, err := proxywasm.GetDownstreamData(0, w.Size)
			if err != nil {
				return false
			}
			return strings.Contains(string(data), "BLOCK")
		}, DoTcpBlock)
}

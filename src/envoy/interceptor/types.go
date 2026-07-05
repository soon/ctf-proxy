package main

import (
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
)

// HttpStage represents the current HTTP lifecycle stage.
type HttpStage int

// TcpStage represents the current TCP lifecycle stage.
type TcpStage int

const undefinedAction types.Action = 0xFFFFFFFF

// An HttpInterceptor is a pair of When/Do functions.
type HttpInterceptor struct {
	// A unique name within a port, for tracing.
	Name string

	// When is called at every stage of the HTTP lifecycle; once it returns true for a stream, it is no longer called for that stream.
	When func(*HttpWhenContext) bool

	// Do will be called once the When matched, at every subsequent stage (including the matching one), until Do returns true.
	Do func(*HttpDoContext) bool
}

// HttpWhenContext provides read-only access for condition evaluation.
type HttpWhenContext struct {
	// Current stage
	Stage HttpStage
	// endOfStream (only meaningful on body stages)
	End bool
	// buffered size visible to the filter
	BodySize int
	// Any data needed to persist between calls by the When function
	Data interface{}

	// Interceptor being executed
	interceptor *HttpInterceptor

	// Retrieves request header by name. Returns "" if not present or not in request stage.
	GetRequestHeader func(name string) string

	// Retrieves request body bytes in the range [start, start+size). Returns nil if not in request stage.
	GetRequestBody func(start, size int) ([]byte, error)

	// Retrieves response header by name. Returns "" if not present or not in response stage.
	GetResponseHeader func(name string) string

	// Retrieves response body bytes in the range [start, start+size). Returns nil if not in response stage.
	GetResponseBody func(start, size int) ([]byte, error)

	// Logs info message to proxy logs with interceptor name prefix
	LogInfo func(message string)

	// By default ActionContinue; set to ActionPause by Pause().
	resultAction types.Action
}

// HttpDoContext provides full access to modify requests and responses.
type HttpDoContext struct {
	Stage HttpStage
	Port  int64
	// endOfStream (only meaningful on body stages)
	End bool
	// buffered size visible to the filter
	BodySize int
	// Any data needed to persist between calls by the When function
	Data interface{}

	interceptor *HttpInterceptor

	// Retrieves request header by name. Returns "" if not present or not in request stage.
	GetRequestHeader func(name string) string

	// Sets request header. Does nothing if not in request stage.
	SetRequestHeader func(name, value string)

	// Deletes request header. Does nothing if not in request stage.
	DelRequestHeader func(name string)

	// Retrieves request body bytes in the range [start, start+size). Returns nil if not in request stage.
	GetRequestBody func(start, size int) ([]byte, error)

	// Replaces entire request body. Does nothing if not in request stage.
	ReplaceRequestBody func([]byte) error

	// Retrieves response header by name. Returns "" if not present or not in response stage.
	GetResponseHeader func(name string) string

	// Sets response header. Does nothing if not in response stage.
	SetResponseHeader func(name, value string)

	// Deletes response header. Does nothing if not in response stage.
	DelResponseHeader func(name string)

	// Retrieves response body bytes in the range [start, start+size). Returns nil if not in response stage.
	GetResponseBody func(start, size int) ([]byte, error)

	// Replaces entire response body. Does nothing if not in response stage.
	ReplaceResponseBody func([]byte) error

	// Logs info message to proxy logs with interceptor name prefix
	LogInfo func(message string)

	// Logs warning message to proxy logs with interceptor name prefix
	LogWarn func(message string)

	// By default ActionContinue; set to ActionPause by Pause().
	resultAction types.Action
}

// Context for a single HTTP stream.
type httpCtx struct {
	types.DefaultHttpContext
	// Skip any further stream processing using this action (undefinedAction by default)
	skip types.Action
	// When contexts for all interceptors defined for this port (if any)
	whenContexts []*HttpWhenContext
	// Do context, once When matched
	doContext *HttpDoContext
}

// A TcpInterceptor is a pair of When/Do functions.
type TcpInterceptor struct {
	// A unique name within a port, for tracing.
	Name string

	// When is called at every stage of the TCP connection; once it returns true for a connection, it is no longer called for that connection.
	When func(*TcpWhenContext) bool

	// Do will be called once the When matched, at every subsequent stage (including the matching one), until Do returns true.
	Do func(*TcpDoContext) bool
}

type TcpWhenContext struct {
	// Current stage
	Stage TcpStage
	// Size of the TCP segment
	Size int
	// endOfStream (only meaningful on body stages)
	End bool

	// Any data needed to persist between calls by the When function
	Data interface{}

	// Interceptor being executed
	interceptor *TcpInterceptor

	// Logs info message to proxy logs with interceptor name prefix
	LogInfo func(message string)

	// By default ActionContinue; set to ActionPause by Pause().
	resultAction types.Action
}

type TcpDoContext struct {
	Stage TcpStage
	Size  int
	// endOfStream (only meaningful on body stages)
	End bool
	// Any data needed to persist between calls by the When function
	Data interface{}

	interceptor *TcpInterceptor
	// By default ActionContinue; set to ActionPause by Pause().
	resultAction types.Action
}

// Context for a single TCP connection.
type tcpCtx struct {
	types.DefaultTcpContext
	// Skip any further stream processing using this action (undefinedAction by default)
	skip types.Action
	// When contexts for all interceptors defined for this port (if any)
	whenContexts []*TcpWhenContext
	// Do context, once When matched
	doContext *TcpDoContext
}

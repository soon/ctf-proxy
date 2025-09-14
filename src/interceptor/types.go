package main

import (
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
)

// Stage represents the current HTTP lifecycle stage.
type Stage int

// An Interceptor is a pair of When/Do functions.
type Interceptor struct {
	// A unique name within a port, for tracing.
	Name string

	// When is called at every stage of the HTTP lifecycle; once it returns true for a stream, it is no longer called for that stream.
	When func(*WhenContext) bool

	// Do will be called once the When matched, at every subsequent stage (including the matching one), until Do returns true.
	Do func(*DoContext) bool
}

// WhenContext provides read-only access for condition evaluation.
type WhenContext struct {
	// Current stage
	Stage Stage
	// endOfStream (only meaningful on body stages)
	End bool
	// buffered size visible to the filter
	BodySize int
	// Any data needed to persist between calls by the When function
	Data interface{}

	// Interceptor being executed
	interceptor *Interceptor

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

// DoContext provides full access to modify requests and responses.
type DoContext struct {
	Stage Stage
	Port  int64
	// endOfStream (only meaningful on body stages)
	End bool
	// buffered size visible to the filter
	BodySize int
	// Any data needed to persist between calls by the When function
	Data interface{}

	interceptor *Interceptor

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

	// By default ActionContinue; set to ActionPause by Pause().
	resultAction types.Action
}

// Context for a single HTTP stream.
type httpCtx struct {
	types.DefaultHttpContext
	// Skip any further stream processing using this action (undefinedAction by default)
	skip types.Action
	// When contexts for all interceptors defined for this port (if any)
	whenContexts []*WhenContext
	// Do context, once When matched
	doContext *DoContext
}

package main

import (
	"encoding/binary"
	"fmt"

	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
)

func getIntProperty(path []string) (int64, error) {
	v, err := proxywasm.GetProperty(path)
	if err != nil {
		return 0, fmt.Errorf("failed to get property %v: %w", path, err)
	}
	if v == nil {
		return 0, fmt.Errorf("property %v not found", path)
	}
	if len(v) != 8 {
		return 0, fmt.Errorf("unexpected property %v length: %d", path, len(v))
	}
	return int64(binary.LittleEndian.Uint64(v)), nil
}

// Human-readable representation of the stage.
func (s HttpStage) String() string {
	switch s {
	case StageRequestHeaders:
		return "req:headers"
	case StageRequestBody:
		return "req:body"
	case StageResponseHeaders:
		return "resp:headers"
	case StageResponseBody:
		return "resp:body"
	default:
		return "unknown"
	}
}

func (s TcpStage) String() string {
	switch s {
	case TcpStageDownstreamData:
		return "down:data"
	case TcpStageUpstreamData:
		return "up:date"
	default:
		return "unknown"
	}
}

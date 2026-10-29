// Session 47 Run 6: compiled once at image build so the module cache and the
// build cache hold pgx before any test runs; the test compiles the served
// snippet beside its own harness with GOPROXY=off.
package main

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

func main() {
	_, _ = pgxpool.ParseConfig("")
	_ = context.Background()
}

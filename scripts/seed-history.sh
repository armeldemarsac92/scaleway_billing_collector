#!/bin/sh
set -eu

exec billing-collector seed-history "$@"

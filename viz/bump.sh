#!/bin/sh
# bump the cache-busting version on every page after editing css/js/data
cd "$(dirname "$0")" && v=$(date +%s) && sed -i '' -E "s#\?v=[0-9]+\"#?v=$v\"#g" *.html && echo "v=$v"

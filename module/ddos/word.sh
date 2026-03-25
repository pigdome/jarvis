#!/bin/bash

wget -q -O - "https://randomword.com" | grep "id=\"random_word\"" | sed "s/^.*\">//g" | sed "s/<.*>//"

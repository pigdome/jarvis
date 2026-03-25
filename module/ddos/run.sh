#!/bin/bash

function ddos
{
    perl attack.pl $1 1000
}

touch ddos.lock

ddos 1 &\
ddos 2 &\
ddos 3 &\
ddos 4

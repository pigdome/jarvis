#!/usr/bin/perl

use strict;
use warnings;

use Koha;

my $version = Koha::version();

print "Koha version : $version\n";

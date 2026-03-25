#!/usr/bin/perl

use Text::CSV;
use Data::Dumper;

no warnings 'utf8';
binmode STDOUT, ":utf8";

my $csv = Text::CSV->new({ binary => 1 });

open my $fh, '<', shift or die $!;

my $header = <$fh>;

$csv->parse($header);
$csv->column_names([$csv->fields]);


while( my $row = $csv->getline_hr($fh) )
{
	# do whatever you want
}

#!/usr/bin/perl

use strict;
use warnings;
use LWP::UserAgent;
use Time::HiRes;

my $id    = shift;
my $count = shift;
my $ua    = new LWP::UserAgent();
my $opac  = "https://tudb.progress.plus";
my $staff = "https://tudb-staff.progress.plus";
my $word;

while ( $count )
{
    my ($interface, $action, $word, $url) = info();
    my $req     = new HTTP::Request ('GET', $url);
    my $start   = [ Time::HiRes::gettimeofday( ) ];
    my $res     = $ua->request($req);
    my $diff    = Time::HiRes::tv_interval( $start );
    my $code    = $res->code;
    
    print qq|[$id][$interface][$action][$code][$word] in $diff\n|;
    
    $count--;
    last unless -e "ddos.lock";
}

sub info
{
    my $percent   = percent();
    my $interface = "STAFF";
    my $action    = "login";
    my $url       = $staff;
    my $word      = "";
    
    if( $percent > 10 )
    {
        $interface = "OPAC";
        if( $percent > 20 )
        {
            $action = "search";
            $word   = qx|./word.sh|;
            chomp $word;
            $url = "$opac/cgi-bin/koha/opac-search.pl?limit=mc-itype,phr:GB&q=$word";
        }
        else
        {
            if( $percent > 15 )
            {
                $action = "corse";
                $url    = "$opac/cgi-bin/koha/opac-course-reserves.pl";
            }
            else
            {
                $action = "corse";
                $url    = "$opac/cgi-bin/koha/opac-course-reserves.pl";
            } 
        }
    }
    return ($interface, $action, $word, $url);
}

sub percent
{
    return int rand 100;
}

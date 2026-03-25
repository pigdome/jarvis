#!/usr/bin/perl

use Encode;

my @lists = (
    { 
        name   => "raberd",
        url    => "https://www.youtube.com/playlist?list=PLcwQy6DvJjszMeyDTvSmELDyMOZf6FygB",
        start  => "19",
        status => 'stop',
    },
    { 
        name   => "chingloy",
        url    => "https://www.youtube.com/playlist?list=PLcwQy6DvJjsyqFVDa-fIfDIwO7gs6gd2c",
        start  => "1",
        end    => "15",
        status => 'stop',
    },
    { 
        name   => "talok",
        url    => "https://www.youtube.com/playlist?list=PLcwQy6DvJjsz4WbvTezGkM7m5p9JApn6O",
        start  => "1",
        end    => "16",
        status => 'stop',
    },
    { 
        name   => "pentor",
        url    => "https://www.youtube.com/playlist?list=PLzBZ3kispW3iGwoNsJ18WpXb0zYC6VtOd",
        start  => "127",
        status => 'ok',
    },
);

foreach my $list ( @lists )
{
    my $name   = $list->{name};
    my $url    = $list->{url};
    my $start  = $list->{start};
    my $stop   = $list->{stop};
    my $status = $list->{status};
    my $reject = $list->{reject};
    my $cmd;

    next unless $status eq "ok";

    $cmd  = qq|youtube-dl -f 18 --yes-playlist |;
    $cmd .= qq|--playlist-start $start | if $start;
    $cmd .= qq|--playlist-stop $stop | if $stop;
    $cmd .= qq|$url|;

    print "$cmd\n";
    system( $cmd );
}


package Mattermost;

use HTTP::Request;
use LWP::UserAgent;
use strict;
use JSON;
use utf8;

use Exporter  qw(import);
our @ISA    = qw(Exporter);
our @EXPORT = qw(new);
our $config = qw|~/.jarvis/config/mattermost.xml|;

sub new 
{
    my $class = shift;
    
    my $self = {};
    
    bless $self,$class;

    $self->config;

    return $self;
}

sub post
{
    my $self  = shift;
    my $text  = shift;
	
	my $req   = $self->{req};
	
	$req->content( encode_json( { text => $text  }  )  );

    my $res   = $self->{ua}->request( $req );

    warn $res->message if $res->is_error;
}

sub config
{
    my $self = shift;

    my $key  = qx|xmllint --xpath "string(/config/mattermost/key)" $config|;
    my $host = qx|xmllint --xpath "string(/config/mattermost/host)" $config|;

    my $req  = HTTP::Request->new( 'POST', "$host/hooks/$key" );
	$req->header( 'Content-Type' => 'application/json' );

	$self->{req} = $req;
    $self->{ua}  = LWP::UserAgent->new;
}

1;


package Redmine;

use LWP::UserAgent;
use strict;
use JSON;
use utf8;

use Exporter  qw(import);
our @ISA    = qw(Exporter);
our @EXPORT = qw(new get);
our $config = qw|~/.jarvis/config/redmine.xml|;

sub new 
{
    my $class = shift;
    
    my $self = {};
    
    bless $self,$class;

    $self->config;

    return $self;
}

sub get
{
    my $self  = shift;
    my $path  = shift;
    my $host  = $self->{host};
    my $res   = $self->{ua}->get( "$host/$path" );


    die $res->message . ",for path $host/$path\n" if $res->is_error;

    return decode_json( $res->content );
}

sub issues
{
	my $self = shift;
	my $iid  = shift;
	my $data = shift;
    
	my $host = $self->{host};
	my $ua   = $self->{ua};

	# get
	return $ua->get( "$host/issues/$iid.json" ) unless $data;
	
	$ua->default_header("Content-Type" => "application/json");

	# post
	return $ua->post( "$host/issues.json", Content => $data ) unless $iid;
	# put
	return $ua->put( "$host/issues/$iid.json" , Content => $data );
}

sub projects
{
	return $_[0]->get("/projects.json?limit=100");
}

sub users
{
	my $self = shift;
	# This endpoint requires admin privileges.
	# so hard code
	my $users;

	foreach my $uid ( qw|4 5 7 8| )
	{
		my $res = $self->get("users/$uid.json");
		$users->{$uid} = $res->{user}->{firstname};
	}

	return $users
}

sub statuses
{
	my $self = shift;

	my $res = $self->get("/issue_statuses.json");
	my $statuses;

	foreach my $status ( @{ $res->{issue_statuses} } )
	{
		my $id   = $status->{id};
		my $name = $status->{name};
		
		$statuses->{$id} = $name;
	}

	return $statuses;
}

sub agile
{
    my $self = shift;
	my $id   = shift;

    my $key   = qx|xmllint --xpath "string(/config/redmine/key)" $config|;
    my $host  = qx|xmllint --xpath "string(/config/redmine/host)" $config|;
    my $count = qx|xmllint --xpath "string(/config/redmine/agiles/agile)" $config|;
	
	my @agiles;
	my $i = 0;

	while ( $i < $count )
	{
    	my $agile = qx|xmllint --xpath "string(/config/redmine/agiles[$i]/agile)" $config|;
		push @agiles, $agile;
		$i++;
	}
}

sub user_agent
{   
    my $key = shift;
    my $ua  = new LWP::UserAgent;

    $ua->timeout(10);
    $ua->ssl_opts( verify_hostname => 0 );
    $ua->default_header( 'X-Redmine-API-Key' => $key );

    return $ua;
}

sub config
{
    my $self = shift;

    my $key  = qx|xmllint --xpath "string(/config/redmine/key)" $config|;
    my $host = qx|xmllint --xpath "string(/config/redmine/host)" $config|;

    $self->{key}  = $key;
    $self->{host} = $host;
    $self->{ua}   = user_agent( $key );
}

1;

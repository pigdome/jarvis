#!/usr/bin/perl

use strict;

my $instance = shift or die "enter instance name";
my $version  = shift or die "enter koha version";
my $kohaconf = "/etc/koha/sites/$instance/koha-conf.xml";

add_apt_sources();
install_koha();
install_maria();
set_required_modules();
create_new_instance();
set_cache_and_plack();
restart_service();

sub add_apt_sources
{
	unless( -e "/etc/apt/sources.list.d/koha.list" )
	{
		print "add sources\n";
		qx|echo deb http://debian.koha-community.org/koha $version main \| sudo tee /etc/apt/sources.list.d/koha.list|;
		qx|wget -O- http://debian.koha-community.org/koha/gpg.asc \| sudo apt-key add -|;
	}
}

sub install_koha
{
	unless( -e "/etc/init.d/koha-common" )
	{
		print "install koha package\n";
		system("sudo apt-get update");
		system("sudo apt-get upgrade");
		system("sudo apt-get clean");
		system("sudo apt-get install koha-common -y");
	}
}

sub install_maria
{
	unless( -e "/etc/init.d/mysql" )
	{
		print "install mariadb\n";
		system("sudo apt-get install mariadb-server -y");
	}
}

sub set_required_modules
{
	system("sudo a2enmod rewrite");
	system("sudo a2enmod cgi");
	system("sudo a2enmod headers proxy_http");
}

sub create_new_instance
{
	system("sudo koha-create --create-db $instance");
}

sub restart_service()
{
	system("sudo service memcached restart");
	system("sudo service koha-common restart");
	system("sudo service apache2 restart");
}

sub set_cache_and_plack
{
	my $template_cache_dir = "/var/cache/koha";
	my $template_cache_dir_text = qx|sudo xmllint --xpath "//config/template_cache_dir/text()" /etc/koha/sites/mea/koha-conf.xml 2> /dev/null |;

	chomp $template_cache_dir_text;

	if( $template_cache_dir_text eq "" )
	{
		qx{sudo sed -i -e "s|<memcached_servers>.*</memcached_servers>|<memcached_servers>localhost:11211</memcached_servers>|g" $kohaconf};
		qx{sudo sed -i -e "s|<memcached_namespace>.*</memcached_namespace>|<memcached_namespace>$instance</memcached_namespace>|g" $kohaconf};
		qx{sudo sed -i -e "s|<template_cache_dir>.*</template_cache_dir>|--><template_cache_dir>$template_cache_dir/$instance</template_cache_dir><!--|g" $kohaconf};
	}

	qx|sudo mkdir $template_cache_dir| unless -d $template_cache_dir;
	qx|sudo mkdir $template_cache_dir/$instance| unless -d "$template_cache_dir/$instance";
	qx|sudo chown $instance-koha:$instance-koha $template_cache_dir/$instance|;

	system("sudo apt-get install memcached") unless -e "/etc/init.d/memcached";
	system("sudo koha-plack --enable $instance");
	system("sudo koha-plack --start $instance") unless -e "/var/run/koha/$instance/plack.sock";
}

sub restart_service()
{
	system("sudo service memcached restart");
	system("sudo service koha-common restart");
	system("sudo service apache2 restart");
}

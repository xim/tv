# TV.py – a hack!

This project is a hack, made so I can watch norwegian TV channels from abroad =)

## Prequisites

 * Python
 * [Pyroutes](http://pyroutes.com/en/latest/installation.html) in the python path.
 * VLC installed


# Deployment

A deployment web server is recommended (Apache2+WSGI tested), but can also run standalone.

## Running as standalone

 * Just run (as root) ./tv.py [listen address]:80

## Deployment in Apache2+WSGI

    <VirtualHost *:443>
    	# If you want SSL – example from my free StartSSL cert
    	SSLEngine on
    	SSLCertificateFile /etc/ssl/certs/tv.crt
    	SSLCertificateKeyFile /etc/ssl/private/tv.key
    	SSLCertificateChainFile /etc/ssl/certs/sub.class1.server.ca.pem
    
    	# If you want to run multiple vhosts on the server
    	ServerName tv.example.com
    	DocumentRoot /your/path/to/tv/
    	<Directory /your/path/to/tv>
    		AllowOverride All
    		Options +FollowSymLinks
    	</Directory>
    	# If you want to restrict user access, make a .htpasswd
    	<Location /listing/>
    		AuthType Basic
    		AuthName "TV over haxx"
    		AuthUserFile /your/path/to/tv/.htpasswd
    		Require valid-user
    	</Location>
    	Alias /media /your/path/to/tv/media
  
    	# Yes, only one process. We only support one client anyways.
    	WSGIDaemonProcess tv processes=1 threads=1
    	WSGIProcessGroup tv
    	WSGIScriptAlias / /your/path/to/tv/tv.py
    
    	# For logging
    	# Possible values include: debug, info, notice, warn, error, crit,
    	# alert, emerg.
    	ErrorLog /var/log/apache2/tv.error.log
    	LogLevel warn
    	CustomLog /var/log/apache2/tv.example.com.access.log combined
    </VirtualHost>
    <VirtualHost *>
    	# If you don't want SSL, use the above config without the SSL bit.
    	# This config is only for SSL hosts.
    	ServerName tv.example.com
    	DocumentRoot /your/path/to/tv/
    	<Directory /your/path/to/tv>
    		AllowOverride All
    		Options +FollowSymLinks
    	</Directory>
    	Redirect /listing https://tv.example.com/listing
    	Alias /media /your/path/to/tv/media
    	WSGIProcessGroup tv
    	WSGIScriptAlias / /your/path/to/tv/tv.py
    
    	ErrorLog /var/log/apache2/tv.error.log
    	LogLevel warn
    	CustomLog /var/log/apache2/tv.access.log combined
    </VirtualHost>

# Showme plugin for Hangoutsbot
A simple plugin to retrieve images accessible to the hangoutsbot server but not necessarily to the client.

## Configuration
The showme plugin requires a dictionary to be added to the hangoutsbot config.json file with the key `showme`.
The dictionary should contain a set of names and source URLs to retrieve images. Any authorization required to retrieve
images from the camera must be included in the URL so this only works with sources that support (the admittedly 
insecure get authorization technique). For example, if you have an IP cameras on your network named "Odin" at IP address 192.168.0.20 where stills can be retrieved from "snapshot.cgi" with user name "admin" and password "2manysecrets" then add the following to your config.json:

```
"showme": {
  "odin": "http://192.168.0.20/snapshot.cgi?user=admin&pwd=2manysecrets"
}
```
Source names are _not_ case sensitive.

## Use
One the plugin has been configured, images can be retrieved by saying `/bot showme <SOURCE>` where `<SOURCE>` is one of the source names in configuration. So for the example above `/bot showme odin` would retrieve a still from the configured camera URL and add it to the current conversation.

You can retrieve a list of configured sources by saying `/bot showme help` or `/bot showme sources`. In either case the bot will reply with it's configured sources.

## Author
Daniel Casner http://www.artificelab.com

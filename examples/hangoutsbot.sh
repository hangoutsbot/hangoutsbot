#! /bin/sh
### BEGIN INIT INFO
# Provides:          hangoutsbot
# Required-Start:    $remote_fs $syslog
# Required-Stop:     $remote_fs $syslog
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: Start hangoutsbot
# Description:       Enable service provided by hangoutsbot chat bot
### END INIT INFO

## Debian (Rasbian) daemon for hangoutsbot chat bot
# @author Daniel Casner <www.danielcasner.org>
#   Please remove the "Author" lines above and replace them
#   with your own name if you copy and modify this script.
# 
# This init.d script allows you to start hangoutsbot automatically when your Raspberry Pi (or other similar linux
# system) starts. This script has been written for and tested on Raspberry Pi Rasbian but it should be trivial to
# modify for other Debian based systems. In order to set up the script, a few steps must be taken in advance:
#
# 1. Run hangoutsbot manually at least once to set up your authorization token
# 2. Move your configuration, cookies and memory files to /etc/hangoutsbot/ or alter the script below to point to where
#    they are.
# 3. The script assumes that hangoutsbot is checked out to /home/pi/hangoutsbot/, if that isn't the case, edit the
#    script below. It also assumes that Python3 is in /usr/local/bin/python3, if your system is different, edit the
#    DAEMON variable in the script below.
# 4. Copy this script to /etc/init.d/hangoutsbot (as in remove the sh from the file name in the desination)
# 5. To auto start on boot execute (once):
#       sudo update-rc.d hangoutsbot defaults
#    To stop auto start on boot execute
#       sudo update-rc.d hangoutsbot remove
# 6. Once you have done that, hangoutsbot will start automatically at boot.
#    You can also start it manually by running
#       sudo /etc/init.d/hangoutsbot start
#    Or stop it manually by running
#       sudo /etc/init.d/hangoutsbot stop
#    Or restart it (to reload the configuration file) by running
#       sudo /etc/init.d/hangoutsbot restart
#
#

# PATH should only include /usr/* if it runs after the mountnfs.sh script
PATH=/sbin:/usr/sbin:/bin:/usr/bin/usr/local/bin:
DESC="hangoutsbot"
NAME=hangoutsbot
RUN_DIR=/var/run/$NAME
ETC_DIR=/etc/$NAME
CONF_FILE=$ETC_DIR/config.json
MAX_RETRIES=1000 # Keep retrying for a long time
DAEMON=/usr/local/bin/python3
DAEMON_ARGS="hangupsbot/hangupsbot.py --log /var/log/hangoutsbot.log --cookies $ETC_DIR/cookies.json --retries=$MAX_RETRIES --memory=$ETC_DIR/memory.json --config $ETC_DIR/config.json"
HOMEDIR=/home/pi/hangoutsbot # Edit if different on your Raspberry Pi
PIDFILE=$RUN_DIR/$NAME.pid
SCRIPTNAME=/etc/init.d/$NAME

# Exit if the package is not installed
[ -x "$DAEMON" ] || exit 0

# Read configuration variable file if it is present
[ -r /etc/default/$NAME ] && . /etc/default/$NAME

# Load the VERBOSE setting and other rcS variables
. /lib/init/vars.sh

# Define LSB log_* functions.
# Depend on lsb-base (>= 3.2-14) to ensure that this file is present
# and status_of_proc is working.
. /lib/lsb/init-functions

#
# Function that starts the daemon/service
#
do_start()
{
		if test ! -d $RUN_DIR; then
      mkdir -p $RUN_DIR
    fi
    if test ! -f $CONF_FILE; then
      echo "No $NAME configuration file at $CONF_FILE. Refusting to start."
      return 2
    fi
    # Return
		#   0 if daemon has been started
		#   1 if daemon was already running
		#   2 if daemon could not be started
		start-stop-daemon --start --quiet --chdir $HOMEDIR --pidfile $PIDFILE --make-pidfile --background --exec $DAEMON --test > /dev/null \
				|| return 1
		start-stop-daemon --start --quiet --chdir $HOMEDIR --pidfile $PIDFILE --make-pidfile --background --exec $DAEMON -- \
				$DAEMON_ARGS \
				|| return 2
		# Add code here, if necessary, that waits for the process to be ready
		# to handle requests from services started subsequently which depend
		# on this one.  As a last resort, sleep for some time.
}

#
# Function that stops the daemon/service
#
do_stop()
{
		# Return
		#   0 if daemon has been stopped
		#   1 if daemon was already stopped
		#   2 if daemon could not be stopped
		#   other if a failure occurred
		start-stop-daemon --stop --quiet --retry=TERM/30/KILL/5 --pidfile $PIDFILE
		RETVAL="$?"
		[ "$RETVAL" = 2 ] && return 2
		# Wait for children to finish too if this is a daemon that forks
		# and if the daemon is only ever run from this initscript.
		# If the above conditions are not satisfied then add some other code
		# that waits for the process to drop all resources that could be
		# needed by services started subsequently.  A last resort is to
		# sleep for some time.
		start-stop-daemon --stop --quiet --oknodo --retry=0/30/KILL/5 --exec $DAEMON
		[ "$?" = 2 ] && return 2
		# Many daemons don't delete their pidfiles when they exit.
		rm -f $PIDFILE
		return "$RETVAL"
}

#
# Function that sends a SIGHUP to the daemon/service
#
do_reload() {
		#
		# If the daemon can reload its configuration without
		# restarting (for example, when it is sent a SIGHUP),
		# then implement that here.
		#
		start-stop-daemon --stop --signal 1 --quiet --pidfile $PIDFILE --name $NAME
		return 0
}

case "$1" in
  start)
		[ "$VERBOSE" != no ] && log_daemon_msg "Starting $DESC" "$NAME"
		do_start
		case "$?" in
				0|1) [ "$VERBOSE" != no ] && log_end_msg 0 ;;
				2) [ "$VERBOSE" != no ] && log_end_msg 1 ;;
		esac
		;;
  stop)
		[ "$VERBOSE" != no ] && log_daemon_msg "Stopping $DESC" "$NAME"
		do_stop
		case "$?" in
				0|1) [ "$VERBOSE" != no ] && log_end_msg 0 ;;
				2) [ "$VERBOSE" != no ] && log_end_msg 1 ;;
		esac
		;;
  status)
		status_of_proc "$DAEMON" "$NAME" && exit 0 || exit $?
		;;
  #reload|force-reload)
		#
		# If do_reload() is not implemented then leave this commented out
		# and leave 'force-reload' as an alias for 'restart'.
		#
		#log_daemon_msg "Reloading $DESC" "$NAME"
		#do_reload
		#log_end_msg $?
		#;;
  restart|force-reload)
		#
		# If the "reload" option is implemented then remove the
		# 'force-reload' alias
		#
		log_daemon_msg "Restarting $DESC" "$NAME"
		do_stop
		case "$?" in
		  0|1)
				do_start
				case "$?" in
						0) log_end_msg 0 ;;
						1) log_end_msg 1 ;; # Old process is still running
						*) log_end_msg 1 ;; # Failed to start
				esac
				;;
		  *)
				# Failed to stop
				log_end_msg 1
				;;
		esac
		;;
  *)
		#echo "Usage: $SCRIPTNAME {start|stop|restart|reload|force-reload}" >&2
		echo "Usage: $SCRIPTNAME {start|stop|status|restart|force-reload}" >&2
		exit 3
		;;
esac

:

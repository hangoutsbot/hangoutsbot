Robot = require('hubot').Robot
Adapter = require('hubot').Adapter
TextMessage = require('hubot').TextMessage
request = require('request')
string = require("string")

# sendmessageURL domain.com/messages/new/channel/ + user.channel
sendMessageUrl = process.env.HUBOT_REST_SEND_URL

class WebAdapter extends Adapter
  toHTML: (message) ->
    # message = string(message).escapeHTML().s
    message.replace(/\n/g, "<br>")

  createUser: (username, room) ->
    user = @userForName username
    unless user?
      id = new Date().getTime().toString()
      user = @userForId id
      user.name = username

    user.room = room

    user

  send: (user, strings...) ->
    if strings.length > 0

      message = if process.env.HUBOT_HTML_RESPONSE then @toHTML(strings.shift()) else strings.shift()

      process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0"

      request.post({ url: "https://127.0.0.1:8081/" + user.room, headers:{'Content-Length': encodeURIComponent(message).length + 8} }).form({
        message: message
      })
      @send user, strings...

  reply: (user, strings...) ->
    @send user, strings.map((str) -> "#{user.user}: #{str}")...

  run: ->
    self = @

    options = {}

    @robot.router.post '/receive/:room', (req, res) ->
      user = self.createUser(req.body.from, req.params.room)

      if req.body.options
        user.options = JSON.parse(req.body.options)
      else
        user.options = {}

      console.log "[#{req.params.room}] #{user.name} => #{req.body.message}"

      res.setHeader 'content-type', 'text/html'
      self.receive new TextMessage(user, req.body.message)
      res.end 'received'

    self.emit "connected"

exports.use = (robot) ->
  new WebAdapter robot

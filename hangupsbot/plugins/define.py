import sys
import plugins
import urllib
import re
from bs4 import BeautifulSoup

def _initialise(bot):
    plugins.register_user_command(["define"])

def define(bot, event, *args):

    argument = str(args)
 
    argument = argument.replace(" ", "-")
  
    argument = re.sub(r'[^\w\s]','', argument)

    url = "http://www.dictionary.com/browse/" + argument + "?s=t"
 
    try:
        response = urllib.request.urlopen(url)
        html = response.read()
     
    except:
           #404 caused by word not found
           yield from bot.coro_send_message(event.conv, "No defenition for " + argument.capitalize())
           return

    soup = BeautifulSoup(html, 'html.parser')

    #word not found
    suggestions = soup.findAll("span", { "class" : "head-entry" })
    for suggestion in suggestions:
        if "Did you mean" in suggestions.get_text():
           yield from bot.coro_send_message(event.conv, "No defenition for " + argument.capitalize())
    
    #word not found
    neverfound = soup.findAll("span")
    for never in neverfound:
        if "no results" in never.get_text():
           yield from bot.coro_send_message(event.conv, "No defenition for " + argument.capitalize())


    nounlist = []
    verblist = []
    adjlist = []
    divs = soup.findAll("div", { "class" : "def-list" })

    
    for div in divs:
        
        sections = div.findAll("section", { "class" : "def-pbk" })

        for section in sections: 
            
            headers = section.findAll("header", { "class" : "luna-data-header" })

            for header in headers:
                
                #find nouns
                if "noun" in header.get_text():    
                   
                   nounlist.insert(0, header.get_text())  

                
                   contents = section.findAll("div", { "class" : "def-set" })
  
                   i = 0
 
                   for content in contents:
                       t = content.get_text()
                       i = i + 1
                       if i < 3:
                          cleaned = t.replace('\n', '')
                          cleaned = re.sub("\s\s+", " ", cleaned)
                          nounlist.append(cleaned)
       
                #find verbs
                if "verb" in header.get_text():    

                   verblist.append(header.get_text())            

                   contents = section.findAll("div", { "class" : "def-set" })
  
                   i = 0
 
                   for content in contents:
                       t = content.get_text()
                       i = i + 1
                       if i < 3:
                          cleaned = t.replace('\n', '')
                          cleaned = re.sub("\s\s+", " ", cleaned)
                          verblist.append(cleaned)  
 
                #find adjectives
                if "adjective" in header.get_text():    

                   verblist.append(header.get_text())            

                   contents = section.findAll("div", { "class" : "def-set" })
  
                   i = 0
 
                   for content in contents:
                       t = content.get_text()
                       i = i + 1
                       if i < 3:
                          cleaned = t.replace('\n', '')
                          cleaned = re.sub("\s\s+", " ", cleaned)
                          verblist.append(cleaned)
           
    #prepare lists    
    nounlist = remove_duplicates(nounlist)
    nounprint = "\n".join(nounlist)
    verbprint = "\n".join(verblist)
    adjprint = "\n".join(adjlist)

          
    tosend = '"<b>' + argument.capitalize() + '</b>"' + "\n\n" + nounprint + "\n\n" + verbprint + "\n\n" + adjprint
    tosend = re.sub(r'\n\n+', r'\n\n', tosend)

    yield from bot.coro_send_message(event.conv, tosend + url)

def remove_duplicates(values):
    output = []
    seen = set()
    for value in values:     
        if value not in seen:
            output.append(value)
            seen.add(value)
    return output
# HARDCODED_RESPONSES — Every User-Visible Response

## Greeting Responses

| Phrase | File | Line | Context |
|---|---|---|---|
| "Hello! I'm Kio, your AI companion." | companion/ | various | Identity greeting |
| "Hey there! How can I help?" | companion/ | various | Standard greeting |
| "Hi! What can I do for you?" | companion/ | various | Standard greeting |
| "I'm Kio, your AI assistant!" | companion/ | various | Identity response |

## Media Responses

| Phrase | File | Line | Context |
|---|---|---|---|
| "🎵 Now playing X by Y" | media_manager.py | various | After successful play |
| "🎵 Now playing X" | media_manager.py | various | After successful play (no artist) |
| "Music paused." | media_manager.py | various | Pause action |
| "Music stopped." | media_manager.py | various | Stop action |
| "Skipping to next track." | media_manager.py | various | Skip action |
| "Going back to previous track." | media_manager.py | various | Previous action |
| "Volume set to X%" | media_manager.py | various | Volume change |
| "No music results found for X" | media_manager.py | various | Search failure |
| "Playing X by Y" | media_manager.py | various | Alternative play response |
| "Resuming playback." | media_manager.py | various | Resume from pause |

## Error Responses

| Phrase | File | Line | Context |
|---|---|---|---|
| "Sorry, I couldn't understand that." | pipeline/__init__.py | various | Intent classification failure |
| "I'm not sure what you mean." | pipeline/__init__.py | various | Fallback response |
| "Something went wrong. Let me try again." | pipeline/__init__.py | various | Error recovery |
| "I don't have access to that right now." | pipeline/__init__.py | various | Permission/capability error |
| "Sorry, I'm having trouble connecting." | llm/ | various | LLM provider failure |
| "No provider available" | llm/ | various | All LLM providers failed |

## Identity/Capability Responses

| Phrase | File | Line | Context |
|---|---|---|---|
| "I'm Kio, your AI companion." | companion/ | various | Identity question |
| "I can help you with music, browsing, and more." | companion/ | various | Capability explanation |
| "I'm here to help!" | companion/ | various | Generic helpful response |
| "I can play music, search the web, and control your browser." | companion/ | various | Capability list |

## Help Responses

| Phrase | File | Line | Context |
|---|---|---|---|
| "Here's what I can do:" | companion/ | various | Help introduction |
| "Try saying 'play some music' to get started." | companion/ | various | Onboarding suggestion |
| "You can ask me to open websites, play music, or search for information." | companion/ | various | Capability suggestion |

## Emergency Responses

| Phrase | File | Line | Context |
|---|---|---|---|
| "I'm here for you. Do you need someone to talk to?" | companion/ | various | Emotional support |
| "If you're in crisis, please reach out to a professional." | companion/ | various | Crisis response |
| "I'm concerned about you. Let me help you find support." | companion/ | various | Concern response |

## Proactive Suggestions

| Phrase | File | Line | Context |
|---|---|---|---|
| "Would you like me to play something?" | proactive_evaluator.py | various | Music suggestion |
| "I noticed you've been working for a while. Need a break?" | proactive_evaluator.py | various | Wellness suggestion |
| "Want me to search for that?" | proactive_evaluator.py | various | Search suggestion |

## Browser Responses

| Phrase | File | Line | Context |
|---|---|---|---|
| "Opening X for you." | browser/ | various | Browser open |
| "Taking a screenshot." | browser/ | various | Screenshot action |
| "I've navigated to X." | browser/ | various | Navigation complete |

## Personality/Companion Responses

| Phrase | File | Line | Context |
|---|---|---|---|
| "I'm always here for you." | companion/ | various | Reassurance |
| "That's a great question!" | companion/ | various | Engagement |
| "Let me think about that..." | companion/ | various | Processing |
| "I appreciate you asking!" | companion/ | various | Gratitude |

## Command Explanations

| Command | Explanation | File |
|---|---|---|
| "play" | Start playing music | companion/_COMMAND_EXPLANATIONS |
| "pause" | Pause current playback | companion/_COMMAND_EXPLANATIONS |
| "stop" | Stop playback entirely | companion/_COMMAND_EXPLANATIONS |
| "next" | Skip to next track | companion/_COMMAND_EXPLANATIONS |
| "previous" | Go back to previous track | companion/_COMMAND_EXPLANATIONS |
| "volume" | Adjust volume level | companion/_COMMAND_EXPLANATIONS |
| "search" | Search for information | companion/_COMMAND_EXPLANATIONS |
| "open" | Open a website or app | companion/_COMMAND_EXPLANATIONS |
| "help" | Show available commands | companion/_COMMAND_EXPLANATIONS |
| "who are you" | Identity information | companion/_COMMAND_EXPLANATIONS |

## Status Messages

| Phrase | File | Line | Context |
|---|---|---|---|
| "Connected to browser." | browser_connector/ | various | WS connection success |
| "Browser disconnected." | browser_connector/ | various | WS disconnect |
| "Media session started." | media_session.py | various | Session start |
| "Media session ended." | media_session.py | various | Session end |
| "Memory saved." | memory/ | various | Memory persistence |
| "Context updated." | context/ | various | Context refresh |

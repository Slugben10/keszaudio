#!/usr/bin/env python3
# Disable screen access check
import os
import sys
import platform

# For macOS, implement comprehensive screen access check bypass
if platform.system() == 'darwin':
    # Set all required environment variables
    os.environ['PYTHONFRAMEWORK'] = '1'
    os.environ['DISPLAY'] = ':0'
    os.environ['WX_NO_DISPLAY_CHECK'] = '1'
    os.environ['OBJC_DISABLE_INITIALIZE_FORK_SAFETY'] = 'YES'
    os.environ['WXMAC_NO_NATIVE_MENUBAR'] = '1'
    os.environ['PYOBJC_DISABLE_CONFIRMATION'] = '1'
    os.environ['QT_MAC_WANTS_LAYER'] = '1'
    os.environ['PYTHONHASHSEED'] = '1' 
    os.environ['WX_NO_NATIVE'] = '1'
    os.environ['PYTHONWARNINGS'] = 'ignore::DeprecationWarning'
    
    # Function to handle uncaught exceptions in the app
    def handle_exception(exc_type, exc_value, exc_traceback):
        import traceback
        error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        
        # Try to show a dialog if possible, otherwise print to stderr
        try:
            import wx
            app = wx.App(False)
            wx.MessageBox(f"An error occurred:\n\n{error_msg}", "Application Error", wx.OK | wx.ICON_ERROR)
            app.MainLoop()
        except:
            sys.stderr.write(f"FATAL ERROR: {error_msg}\n")
        
        # Exit with error code
        sys.exit(1)
    
    # Set the exception handler
    sys.excepthook = handle_exception

    # Try to patch wxPython directly
    try:
        import wx
        
        # Patch wx.App to avoid screen check
        if hasattr(wx, 'App'):
            original_init = wx.App.__init__
            
            def patched_init(self, *args, **kwargs):
                # Force redirect to False to avoid screen check issues
                kwargs['redirect'] = False
                return original_init(self, *args, **kwargs)
            
            wx.App.__init__ = patched_init
        
        # Try to patch _core directly
        if hasattr(wx, '_core'):
            if hasattr(wx._core, '_macIsRunningOnMainDisplay'):
                # Replace with function that always returns True
                wx._core._macIsRunningOnMainDisplay = lambda: True
    except Exception as e:
        # Not a fatal error, just log it
        print(f"Warning: Could not patch wxPython components: {e}")

import json
import shutil
import tempfile
import threading
import time
from datetime import datetime
import requests
import base64
from io import BytesIO
import openai
from openai import OpenAI
import wave
import uuid
import re
import io
import subprocess
import hashlib
import pickle
import types
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

# Make wx imports without errors
import wx
import wx.adv

# Try to import other dependencies with graceful fallback
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    import librosa
    import soundfile as sf
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False

# Check if pydub is available for audio conversion
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False

# Check if pyannote is available for speaker diarization
try:
    import torch
    import pyannote.audio
    from pyannote.audio.pipelines.speaker_verification import PretrainedSpeakerEmbedding
    from pyannote.audio import Audio
    from pyannote.core import Segment, Annotation
    PYANNOTE_AVAILABLE = True
except ImportError:
    PYANNOTE_AVAILABLE = False

# Make PyAudio optional with silent failure
try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except:
    PYAUDIO_AVAILABLE = False

# Ensure required directories exist
def ensure_directories():
    """Create necessary directories if they don't exist."""
    import os
    import platform
    import sys
    from pathlib import Path
    
    # For macOS app bundle, use proper app storage locations
    if platform.system() == 'darwin' and getattr(sys, 'frozen', False):
        try:
            # Use ~/Documents for user data
            home_dir = Path.home()
            app_name = "Audio Processing App"
            
            # Create app directory in Documents
            app_dir = home_dir / "Documents" / app_name
            
            # Define required directories
            directories = [
                app_dir,
                app_dir / "Transcripts", 
                app_dir / "Summaries",
                app_dir / "diarization_cache"
            ]
            
            # Create the directories if they don't exist
            for directory in directories:
                if not directory.exists():
                    try:
                        directory.mkdir(parents=True, exist_ok=True)
                        print(f"Created directory: {directory}")
                    except Exception as e:
                        print(f"Error creating directory {directory}: {e}")
            
            # Return the app directory path for reference
            return str(app_dir)
        except Exception as e:
            # If we can't create directories in Documents, create them in /tmp as a fallback
            print(f"Error creating directories in Documents: {e}")
            try:
                tmp_dir = Path("/tmp") / "AudioProcessingApp"
                tmp_dir.mkdir(parents=True, exist_ok=True)
                
                # Create subdirectories
                (tmp_dir / "Transcripts").mkdir(exist_ok=True)
                (tmp_dir / "Summaries").mkdir(exist_ok=True)
                (tmp_dir / "diarization_cache").mkdir(exist_ok=True)
                
                print(f"Created temporary directories in {tmp_dir}")
                return str(tmp_dir)
            except Exception as e2:
                print(f"Failed to create directories in /tmp: {e2}")
                # Return current directory as a last resort
                return os.path.abspath('.')
    else:
        # For normal terminal execution, use relative paths but first check if they can be created
        try:
            directories = ["Transcripts", "Summaries", "diarization_cache"]
            for directory in directories:
                if not os.path.exists(directory):
                    os.makedirs(directory)
            
            # Return current directory for reference
            return os.path.abspath('.')
        except OSError as e:
            # If we can't create in current directory, try user's home directory
            print(f"Error creating directories in current path: {e}")
            try:
                home_dir = Path.home()
                app_dir = home_dir / "AudioProcessingApp"
                app_dir.mkdir(parents=True, exist_ok=True)
                
                # Create subdirectories
                (app_dir / "Transcripts").mkdir(exist_ok=True)
                (app_dir / "Summaries").mkdir(exist_ok=True)
                (app_dir / "diarization_cache").mkdir(exist_ok=True)
                
                print(f"Created directories in {app_dir}")
                return str(app_dir)
            except Exception as e2:
                print(f"Failed to create directories in home directory: {e2}")
                # Return current directory as a last resort, even if we can't write to it
                return os.path.abspath('.')

# Global variables
APP_BASE_DIR = None  # Application base directory 
app_name = "Audio Processing App"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
WHISPER_MODEL = "whisper-1"
client = None  # OpenAI client instance

# Disable GUI requirement check for wxPython
os.environ['WXSUPPRESS_SIZER_FLAGS_CHECK'] = '1'
os.environ['WXSUPPRESS_APP_NAME_WARNING'] = '1'

# Add new imports for speaker diarization with graceful fallback
DIARIZATION_AVAILABLE = False
try:
    from pyannote.audio import Pipeline
    from pyannote.core import Segment, Timeline, Annotation
    import torch
    DIARIZATION_AVAILABLE = True
except ImportError:
    # Silently set flag without showing warning
    pass


# Simple CLI version for when GUI is not available
def run_cli():
    print("\n========= AI Assistant (CLI Mode) =========")
    print("1. Set OpenAI API Key")
    print("2. Transcribe Audio")
    print("3. Chat with AI")
    print("4. Exit")
    
    api_key = os.environ.get("OPENAI_API_KEY", "")
    client = None
    if api_key:
        try:
            client = OpenAI(api_key=api_key)
            print("OpenAI API Key found in environment.")
        except Exception as e:
            print(f"Error initializing OpenAI client: {e}")
    
    while True:
        choice = input("\nEnter your choice (1-4): ")
        
        if choice == "1":
            api_key = input("Enter your OpenAI API Key: ").strip()
            os.environ["OPENAI_API_KEY"] = api_key
            try:
                client = OpenAI(api_key=api_key)
                print("API Key set successfully.")
            except Exception as e:
                print(f"Error setting API key: {e}")
        
        elif choice == "2":
            if not client:
                print("Please set your OpenAI API Key first (option 1).")
                continue
                
            audio_path = input("Enter the path to your audio file: ").strip()
            if not os.path.exists(audio_path):
                print(f"File not found: {audio_path}")
                continue
                
            print("Transcribing audio...")
            try:
                with open(audio_path, "rb") as audio_file:
                    response = client.audio.transcriptions.create(
                        file=audio_file,
                        model="whisper-1"
                    )
                print("\n--- Transcription ---")
                print(response.text)
                print("---------------------")
            except Exception as e:
                print(f"Error transcribing audio: {e}")
        
        elif choice == "3":
            if not client:
                print("Please set your OpenAI API Key first (option 1).")
                continue
                
            print("\nChat with AI (type 'exit' to end conversation)")
            chat_history = []
            
            while True:
                user_input = input("\nYou: ")
                if user_input.lower() == 'exit':
                    break
                    
                chat_history.append({"role": "user", "content": user_input})
                
                try:
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=chat_history,
                        temperature=0.7,
                        max_tokens=1000
                    )
                    
                    assistant_message = response.choices[0].message.content
                    chat_history.append({"role": "assistant", "content": assistant_message})
                    
                    print(f"\nAssistant: {assistant_message}")
                except Exception as e:
                    print(f"Error: {e}")
        
        elif choice == "4":
            print("Exiting AI Assistant. Goodbye!")
            break
            
        else:
            print("Invalid choice. Please enter a number between 1 and 4.")


def main():
    # Check if we're running in CLI mode explicitly
    if "--cli" in sys.argv:
        run_cli()
        return 0
    
    # Check if wxPython is available
    if not WX_AVAILABLE:
        print("wxPython is not available. Running in CLI mode.")
        run_cli()
        return 0
    
    # Try to run in GUI mode
    try:
        app = MainApp()
        app.MainLoop()
        return 0
    except Exception as e:
        print(f"Error starting application: {e}")
        print("Falling back to CLI mode.")
        run_cli()
        return 1

class AudioProcessor:
    """Audio processing functionality for transcription and diarization."""
    def __init__(self, client, update_callback=None, config_manager=None):
        self.client = client
        self.update_callback = update_callback
        self.config_manager = config_manager
        self.transcript = None  # Initialize transcript attribute
    
    def update_status(self, message, percent=None):
        """Update status with message and optional progress percentage."""
        if self.update_callback:
            self.update_callback(message, percent)
    
    def transcribe_audio(self, audio_path, language=None):
        """Transcribe audio file using OpenAI's Whisper API."""
        try:
            if not self.client:
                error_msg = "Error: OpenAI client not initialized"
                self.transcript = error_msg
                return error_msg
            
            self.update_status("Transcribing audio...", percent=10)
            
            with open(audio_path, "rb") as audio_file:
                response = self.client.audio.transcriptions.create(
                    file=audio_file,
                    model=WHISPER_MODEL,
                    language=language
                )
            
            self.update_status("Transcription complete", percent=100)
            self.transcript = response.text  # Store the transcript as an attribute
            return response.text
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            self.update_status(f"Error transcribing audio: {str(e)}", percent=0)
            self.transcript = error_msg  # Set transcript to error message to avoid None
            return error_msg
            
    def _get_ffmpeg_install_instructions(self):
        """Return platform-specific FFmpeg installation instructions."""
        import platform
        system = platform.system().lower()
        
        if system == 'darwin':  # macOS
            return "On macOS:\n1. Install Homebrew from https://brew.sh if you don't have it\n2. Run: brew install ffmpeg"
        elif system == 'windows':
            return "On Windows:\n1. Download from https://ffmpeg.org/download.html\n2. Add to PATH or use a package manager like Chocolatey (choco install ffmpeg)"
        elif system == 'linux':
            return "On Linux:\n- Ubuntu/Debian: sudo apt install ffmpeg\n- Fedora: sudo dnf install ffmpeg\n- Arch: sudo pacman -S ffmpeg"
        else:
            return "Please download FFmpeg from https://ffmpeg.org/download.html"

class MainApp(wx.App):
    def OnInit(self):
        try:
            # Force GUI to work on macOS without Framework build
            self.SetExitOnFrameDelete(True)
            self.frame = MainFrame(None, title="AI Assistant", base_dir=APP_BASE_DIR)
            self.frame.Show()
            # Set top window explicitly for macOS
            self.SetTopWindow(self.frame)
            return True
        except AttributeError as e:
            # Add missing methods to MainFrame that might be referenced but don't exist
            if "'MainFrame' object has no attribute" in str(e):
                attr_name = str(e).split("'")[-2]
                print(f"Adding missing attribute: {attr_name}")
                setattr(MainFrame, attr_name, lambda self, *args, **kwargs: None)
                # Try again
                return self.OnInit()
            else:
                print(f"Error initializing main frame: {e}")
                return False
        except Exception as e:
            print(f"Error initializing main frame: {e}")
            return False

class MainFrame(wx.Frame):
    def __init__(self, parent, title, base_dir):
        super(MainFrame, self).__init__(parent, title=title, size=(1200, 800))
        
        # Initialize config manager
        self.config_manager = ConfigManager(base_dir)
        
        # Initialize attributes
        self.client = None
        self.api_key = self.config_manager.get_api_key()
        self.language = self.config_manager.get_language() or "en"
        self.hf_token = self.config_manager.get_pyannote_token()
        
        # Initialize other attributes that might be referenced
        self.identify_speakers_btn = None
        self.speaker_id_help_text = None
        self.transcript = None
        self.last_audio_path = None
        
        # Check for API key and initialize client
        self.initialize_openai_client()
        
        # Initialize processors
        self.audio_processor = AudioProcessor(client, self.update_status, self.config_manager)
        self.llm_processor = LLMProcessor(client, self.config_manager, self.update_status)
        
        # Set up the UI - use either create_ui or init_ui, not both
        # Initialize menus and status bar using create_ui
        self.create_ui() # Create notebook and panels
        
        # Event bindings
        self.bind_events()
        
        # Center the window
        self.Centre()
        
        # Status update
        self.update_status("Application ready.", percent=0)
        
        # Display info about supported audio formats
        wx.CallLater(1000, self.show_format_info)
        
        # Check for PyAnnote and display installation message if needed
        wx.CallLater(1500, self.check_pyannote)
    
    def initialize_openai_client(self):
        """Initialize OpenAI client with API key."""
        global client
        api_key = self.config_manager.get_api_key()
        
        if not api_key:
            dlg = wx.TextEntryDialog(self, "Please enter your OpenAI API key:", "API Key Required")
            if dlg.ShowModal() == wx.ID_OK:
                api_key = dlg.GetValue()
                self.config_manager.set_api_key(api_key)
            dlg.Destroy()
        
        try:
            client = OpenAI(api_key=api_key)
        except Exception as e:
            wx.MessageBox(f"Error initializing OpenAI client: {str(e)}", "Error", wx.OK | wx.ICON_ERROR)
            
    def create_ui(self):
        """Create the user interface."""
        # Create status bar
        self.status_bar = self.CreateStatusBar()
        self.status_bar.SetStatusText("Ready")
        
        # Create menu bar
        menu_bar = wx.MenuBar()
        
        # File menu
        file_menu = wx.Menu()
        
        # Audio submenu
        audio_menu = wx.Menu()
        upload_audio_item = audio_menu.Append(wx.ID_ANY, "&Upload Audio File", "Upload audio file for transcription")
        self.Bind(wx.EVT_MENU, self.on_upload_audio, upload_audio_item)
        
        file_menu.AppendSubMenu(audio_menu, "&Audio")
        
        # Document submenu
        doc_menu = wx.Menu()
        upload_doc_item = doc_menu.Append(wx.ID_ANY, "&Upload Document", "Upload document for LLM context")
        select_docs_item = doc_menu.Append(wx.ID_ANY, "&Select Documents", "Select documents to load into context")
        
        self.Bind(wx.EVT_MENU, self.on_upload_document, upload_doc_item)
        self.Bind(wx.EVT_MENU, self.on_select_documents, select_docs_item)
        
        file_menu.AppendSubMenu(doc_menu, "&Documents")
        
        # Settings menu item
        settings_item = file_menu.Append(wx.ID_ANY, "&Settings", "Application settings")
        self.Bind(wx.EVT_MENU, self.on_settings, settings_item)
        
        # Exit menu item
        exit_item = file_menu.Append(wx.ID_EXIT, "E&xit", "Exit application")
        self.Bind(wx.EVT_MENU, self.on_exit, exit_item)
        
        menu_bar.Append(file_menu, "&File")
        
        # Help menu
        help_menu = wx.Menu()
        about_item = help_menu.Append(wx.ID_ABOUT, "&About", "About this application")
        self.Bind(wx.EVT_MENU, self.on_about, about_item)
        
        menu_bar.Append(help_menu, "&Help")
        
        self.SetMenuBar(menu_bar)
        
        # Create notebook for tabbed interface
        self.notebook = wx.Notebook(self)
        
        # Create panels for each tab
        self.audio_panel = wx.Panel(self.notebook)
        self.chat_panel = wx.Panel(self.notebook)
        self.settings_panel = wx.Panel(self.notebook)
        
        # Add panels to notebook
        self.notebook.AddPage(self.audio_panel, "Audio Processing")
        self.notebook.AddPage(self.chat_panel, "Chat")
        self.notebook.AddPage(self.settings_panel, "Settings")
        
        # Bind the notebook page change event
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_notebook_page_changed)
        
        # Create UI for each panel
        if hasattr(self, 'create_audio_panel'):
            self.create_audio_panel()
        
        # Add placeholder method if not exists
        if not hasattr(self, 'create_chat_panel'):
            def create_chat_panel(self):
                chat_sizer = wx.BoxSizer(wx.VERTICAL)
                placeholder = wx.StaticText(self.chat_panel, label="Chat panel")
                chat_sizer.Add(placeholder, 1, wx.EXPAND | wx.ALL, 5)
                self.chat_panel.SetSizer(chat_sizer)
            self.create_chat_panel = types.MethodType(create_chat_panel, self)
        self.create_chat_panel()
        
        # Add placeholder method if not exists
        if not hasattr(self, 'create_settings_panel'):
            def create_settings_panel(self):
                settings_sizer = wx.BoxSizer(wx.VERTICAL)
                placeholder = wx.StaticText(self.settings_panel, label="Settings panel")
                settings_sizer.Add(placeholder, 1, wx.EXPAND | wx.ALL, 5)
                self.settings_panel.SetSizer(settings_sizer)
            self.create_settings_panel = types.MethodType(create_settings_panel, self)
        self.create_settings_panel()
        
        # Main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 5)
        
        self.SetSizer(main_sizer)
        
    def on_notebook_page_changed(self, event):
        """Handle notebook page change event."""
        old_page = event.GetOldSelection()
        new_page = event.GetSelection()
        
        # If user switched from settings to audio tab, update the speaker ID button styling
        if old_page == 2 and new_page == 0:  # 2 = settings, 0 = audio
            self.identify_speakers_btn.SetLabel(self.get_speaker_id_button_label())
            self.speaker_id_help_text.SetLabel(self.get_speaker_id_help_text())
            self.update_speaker_id_button_style()
            self.audio_panel.Layout()
            
        event.Skip()  # Allow default event processing
    
    def get_speaker_id_button_label(self):
        """Get label for speaker identification button based on token availability."""
        has_token = bool(self.config_manager.get_pyannote_token())
        return "Identify Speakers (Advanced)" if has_token else "Identify Speakers (Basic)"
    
    def get_speaker_id_help_text(self):
        """Get help text for speaker identification based on token availability."""
        has_token = bool(self.config_manager.get_pyannote_token())
        if has_token:
            return "Using PyAnnote for advanced speaker identification"
        else:
            return "Using basic speaker identification (Add PyAnnote token in Settings for better results)"
            
    def update_speaker_id_button_style(self):
        """Update the style of the speaker identification button based on token availability."""
        if hasattr(self, 'identify_speakers_btn'):
            has_token = bool(self.config_manager.get_pyannote_token())
            if has_token:
                self.identify_speakers_btn.SetBackgroundColour(wx.Colour(50, 200, 50))
            else:
                self.identify_speakers_btn.SetBackgroundColour(wx.NullColour)
    
    def check_api_key(self):
        """Check if API key is available and initialize the client."""
        api_key = self.config_manager.get_api_key()
        
        if api_key:
            try:
                self.client = OpenAI(api_key=api_key)
                self.status_bar.SetStatusText("API Key loaded from configuration")
                return
            except Exception as e:
                print(f"Error loading API key from configuration: {e}")
        
        # If API key is not in config or invalid, ask the user
        self.show_api_key_dialog()
    
    def show_api_key_dialog(self):
        """Show dialog to enter API key."""
        dialog = wx.TextEntryDialog(self, "Please enter your OpenAI API Key:", "API Key Required")
        if dialog.ShowModal() == wx.ID_OK:
            api_key = dialog.GetValue().strip()
            if api_key:
                # Save the API key to configuration
                self.config_manager.set_api_key(api_key)
                
                try:
                    self.client = OpenAI(api_key=api_key)
                    self.status_bar.SetStatusText("API Key saved")
                except Exception as e:
                    wx.MessageBox(f"Error initializing OpenAI client: {e}", "Error", wx.OK | wx.ICON_ERROR)
                    self.show_api_key_dialog()
            else:
                wx.MessageBox("API Key is required to use this application.", "Error", wx.OK | wx.ICON_ERROR)
                self.show_api_key_dialog()
        else:
            wx.MessageBox("API Key is required to use this application.", "Error", wx.OK | wx.ICON_ERROR)
            self.show_api_key_dialog()
        dialog.Destroy()
    
    def init_ui(self):
        # Create status bar
        self.status_bar = self.CreateStatusBar()
        self.status_bar.SetStatusText("Ready")
        
        # Create menu bar
        menu_bar = wx.MenuBar()
        
        # File menu
        file_menu = wx.Menu()
        
        # Audio submenu
        audio_menu = wx.Menu()
        upload_audio_item = audio_menu.Append(wx.ID_ANY, "&Upload Audio File", "Upload audio file for transcription")
        self.Bind(wx.EVT_MENU, self.on_upload_audio, upload_audio_item)
        
        file_menu.AppendSubMenu(audio_menu, "&Audio")
        
        # Document submenu
        doc_menu = wx.Menu()
        upload_doc_item = doc_menu.Append(wx.ID_ANY, "&Upload Document", "Upload document for LLM context")
        select_docs_item = doc_menu.Append(wx.ID_ANY, "&Select Documents", "Select documents to load into context")
        
        self.Bind(wx.EVT_MENU, self.on_upload_document, upload_doc_item)
        self.Bind(wx.EVT_MENU, self.on_select_documents, select_docs_item)
        
        file_menu.AppendSubMenu(doc_menu, "&Documents")
        
        # Settings menu item
        settings_item = file_menu.Append(wx.ID_ANY, "&Settings", "Application settings")
        self.Bind(wx.EVT_MENU, self.on_settings, settings_item)
        
        # Exit menu item
        exit_item = file_menu.Append(wx.ID_EXIT, "E&xit", "Exit application")
        self.Bind(wx.EVT_MENU, self.on_exit, exit_item)
        
        menu_bar.Append(file_menu, "&File")
        
        # Help menu
        help_menu = wx.Menu()
        about_item = help_menu.Append(wx.ID_ABOUT, "&About", "About this application")
        self.Bind(wx.EVT_MENU, self.on_about, about_item)
        
        menu_bar.Append(help_menu, "&Help")
        
        self.SetMenuBar(menu_bar)
        
        # Main panel with notebook
        self.panel = wx.Panel(self)
        self.notebook = wx.Notebook(self.panel)
        
        # Chat tab
        self.chat_tab = wx.Panel(self.notebook)
        chat_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Chat history
        self.chat_display = wx.TextCtrl(self.chat_tab, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        
        # Input area
        input_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.chat_input = wx.TextCtrl(self.chat_tab, style=wx.TE_MULTILINE)
        send_button = wx.Button(self.chat_tab, label="Send")
        
        input_sizer.Add(self.chat_input, proportion=1, flag=wx.EXPAND | wx.RIGHT, border=5)
        input_sizer.Add(send_button, proportion=0, flag=wx.EXPAND)
        
        chat_sizer.Add(self.chat_display, proportion=1, flag=wx.EXPAND | wx.ALL, border=5)
        chat_sizer.Add(input_sizer, proportion=0, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=5)
        
        self.chat_tab.SetSizer(chat_sizer)
        
        # Transcription tab
        self.transcription_tab = wx.Panel(self.notebook)
        transcription_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Transcription display
        self.transcription_display = wx.TextCtrl(self.transcription_tab, style=wx.TE_MULTILINE | wx.TE_RICH2)
        
        # Speaker panel
        speaker_panel = wx.Panel(self.transcription_tab)
        speaker_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.speaker_list = wx.ListCtrl(speaker_panel, style=wx.LC_REPORT)
        self.speaker_list.InsertColumn(0, "Speaker")
        self.speaker_list.InsertColumn(1, "Name")
        
        speaker_button_sizer = wx.BoxSizer(wx.VERTICAL)
        rename_speaker_button = wx.Button(speaker_panel, label="Rename Speaker")
        regenerate_button = wx.Button(speaker_panel, label="Regenerate Transcript")
        
        speaker_button_sizer.Add(rename_speaker_button, flag=wx.EXPAND | wx.BOTTOM, border=5)
        speaker_button_sizer.Add(regenerate_button, flag=wx.EXPAND)
        
        speaker_sizer.Add(self.speaker_list, proportion=1, flag=wx.EXPAND | wx.RIGHT, border=5)
        speaker_sizer.Add(speaker_button_sizer, proportion=0, flag=wx.EXPAND)
        
        speaker_panel.SetSizer(speaker_sizer)
        
        # Summarization panel
        summary_panel = wx.Panel(self.transcription_tab)
        summary_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        templates_label = wx.StaticText(summary_panel, label="Template:")
        self.templates_combo = wx.ComboBox(summary_panel, choices=["Meeting Notes", "Interview Summary", "Lecture Notes"])
        summarize_button = wx.Button(summary_panel, label="Summarize")
        
        summary_sizer.Add(templates_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5)
        summary_sizer.Add(self.templates_combo, proportion=1, flag=wx.EXPAND | wx.RIGHT, border=5)
        summary_sizer.Add(summarize_button, proportion=0, flag=wx.EXPAND)
        
        summary_panel.SetSizer(summary_sizer)
        
        transcription_sizer.Add(self.transcription_display, proportion=1, flag=wx.EXPAND | wx.ALL, border=5)
        transcription_sizer.Add(speaker_panel, proportion=0, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=5)
        transcription_sizer.Add(summary_panel, proportion=0, flag=wx.EXPAND | wx.ALL, border=5)
        
        self.transcription_tab.SetSizer(transcription_sizer)
        
        # Settings tab (NEW)
        self.settings_tab = wx.Panel(self.notebook)
        settings_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # API Keys section
        api_box = wx.StaticBox(self.settings_tab, label="API Keys")
        api_box_sizer = wx.StaticBoxSizer(api_box, wx.VERTICAL)
        
        # OpenAI API Key
        openai_sizer = wx.BoxSizer(wx.HORIZONTAL)
        openai_label = wx.StaticText(self.settings_tab, label="OpenAI API Key:")
        self.openai_input = wx.TextCtrl(self.settings_tab, value=self.api_key, style=wx.TE_PASSWORD)
        
        openai_sizer.Add(openai_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5)
        openai_sizer.Add(self.openai_input, proportion=1)
        
        # HuggingFace API Key
        hf_sizer = wx.BoxSizer(wx.HORIZONTAL)
        hf_label = wx.StaticText(self.settings_tab, label="HuggingFace Token:")
        self.hf_input = wx.TextCtrl(self.settings_tab, value=self.hf_token, style=wx.TE_PASSWORD)
        
        hf_sizer.Add(hf_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5)
        hf_sizer.Add(self.hf_input, proportion=1)
        
        api_box_sizer.Add(openai_sizer, flag=wx.EXPAND | wx.ALL, border=5)
        api_box_sizer.Add(hf_sizer, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=5)
        
        # Language settings section
        lang_box = wx.StaticBox(self.settings_tab, label="Language Settings")
        lang_box_sizer = wx.StaticBoxSizer(lang_box, wx.VERTICAL)
        
        lang_sizer = wx.BoxSizer(wx.HORIZONTAL)
        lang_label = wx.StaticText(self.settings_tab, label="Transcription Language:")
        self.lang_combo = wx.ComboBox(self.settings_tab, 
                                     choices=["English (en)", "Hungarian (hu)"],
                                     style=wx.CB_READONLY)
        
        # Set initial selection based on saved language
        if self.language == "hu":
            self.lang_combo.SetSelection(1)  # Hungarian
        else:
            self.lang_combo.SetSelection(0)  # Default to English
        
        lang_sizer.Add(lang_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5)
        lang_sizer.Add(self.lang_combo, proportion=1)
        
        lang_box_sizer.Add(lang_sizer, flag=wx.EXPAND | wx.ALL, border=5)
        
        # Save button for settings
        save_button = wx.Button(self.settings_tab, label="Save Settings")
        save_button.Bind(wx.EVT_BUTTON, self.on_save_settings)
        
        # Add all sections
        settings_sizer.Add(api_box_sizer, flag=wx.EXPAND | wx.ALL, border=10)
        settings_sizer.Add(lang_box_sizer, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=10)
        settings_sizer.Add(save_button, flag=wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=10)
        
        self.settings_tab.SetSizer(settings_sizer)
        
        # Add tabs to notebook
        self.notebook.AddPage(self.chat_tab, "Chat")
        self.notebook.AddPage(self.transcription_tab, "Transcription")
        self.notebook.AddPage(self.settings_tab, "Settings")
        
        # Main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(self.notebook, proportion=1, flag=wx.EXPAND | wx.ALL, border=5)
        
        self.panel.SetSizer(main_sizer)
        
        # Bind events
        send_button.Bind(wx.EVT_BUTTON, self.on_send_message)
        self.chat_input.Bind(wx.EVT_KEY_DOWN, self.on_key_down)
        rename_speaker_button.Bind(wx.EVT_BUTTON, self.on_rename_speaker)
        regenerate_button.Bind(wx.EVT_BUTTON, self.on_regenerate_transcript)
        summarize_button.Bind(wx.EVT_BUTTON, self.on_summarize)
    
    def on_key_down(self, event):
        key_code = event.GetKeyCode()
        if key_code == wx.WXK_RETURN and event.ShiftDown():
            # Allow Shift+Enter to insert a newline
            event.Skip()
        elif key_code == wx.WXK_RETURN:
            # Enter key sends the message
            self.on_send_message(event)
        else:
            event.Skip()
    
    def on_send_message(self, event):
        """Handle sending a message in the chat."""
        user_input = self.user_input.GetValue()
        if not user_input:
            return
            
        # Generate response
        response = self.llm_processor.generate_response(user_input)
        
        # Update chat history
        self.chat_history_text.AppendText(f"You: {user_input}\n")
        self.chat_history_text.AppendText(f"Assistant: {response}\n\n")
        
        # Clear user input
        self.user_input.SetValue("")
        
    def on_clear_chat_history(self, event):
        """Clear the chat history."""
        self.llm_processor.clear_chat_history()
        self.chat_history_text.SetValue("")
        
    def on_save_api_key(self, event):
        """Save the API key."""
        api_key = self.api_key_input.GetValue()
        self.config_manager.set_api_key(api_key)
        wx.MessageBox("API key saved successfully.", "Success", wx.OK | wx.ICON_INFORMATION)
        
    def on_save_pyannote_token(self, event):
        """Save the PyAnnote token."""
        token = self.pyannote_token_input.GetValue()
        self.config_manager.set_pyannote_token(token)
        
        # Update the speaker identification button style
        self.identify_speakers_btn.SetLabel(self.get_speaker_id_button_label())
        self.speaker_id_help_text.SetLabel(self.get_speaker_id_help_text())
        self.update_speaker_id_button_style()
        self.audio_panel.Layout()
        
        wx.MessageBox("PyAnnote token saved successfully.", "Success", wx.OK | wx.ICON_INFORMATION)
        
    def on_save_model(self, event):
        """Save the selected model."""
        model = self.model_choice.GetString(self.model_choice.GetSelection())
        self.config_manager.set_model(model)
        wx.MessageBox("Model saved successfully.", "Success", wx.OK | wx.ICON_INFORMATION)
        
    def on_save_temperature(self, event):
        """Save the temperature value."""
        temperature = self.temperature_slider.GetValue() / 10.0
        self.config_manager.set_temperature(temperature)
        wx.MessageBox("Temperature saved successfully.", "Success", wx.OK | wx.ICON_INFORMATION)
        
    def on_save_language(self, event):
        """Save the selected language."""
        language = self.language_settings_choice.GetString(self.language_settings_choice.GetSelection()).lower()
        self.config_manager.set_language(language)
        wx.MessageBox("Language saved successfully.", "Success", wx.OK | wx.ICON_INFORMATION)
        
    def populate_template_list(self):
        """Populate the template list with available templates."""
        self.template_list.Clear()
        templates = self.config_manager.get_templates()
        for name in templates.keys():
            self.template_list.Append(name)
            
    def on_add_template(self, event):
        """Add a new template."""
        name = self.template_name_input.GetValue()
        content = self.template_content_input.GetValue()
        
        if not name or not content:
            wx.MessageBox("Please enter both name and content for the template.", "Error", wx.OK | wx.ICON_ERROR)
            return
            
        self.config_manager.add_template(name, content)
        self.populate_template_list()
        self.template_name_input.SetValue("")
        self.template_content_input.SetValue("")
        
    def on_remove_template(self, event):
        """Remove the selected template."""
        selected = self.template_list.GetSelection()
        if selected == wx.NOT_FOUND:
            wx.MessageBox("Please select a template to remove.", "Error", wx.OK | wx.ICON_ERROR)
            return
            
        template_name = self.template_list.GetString(selected)
        
        # Confirm deletion
        dlg = wx.MessageDialog(self, f"Are you sure you want to delete the template '{template_name}'?",
                              "Confirm Deletion", wx.YES_NO | wx.ICON_QUESTION)
        if dlg.ShowModal() == wx.ID_YES:
            # Delete template
            self.config_manager.remove_template(template_name)
            
            # Update lists
            self.populate_template_list()
            
            # Update template choice in audio panel
            templates = list(self.config_manager.get_templates().keys())
            self.template_choice.SetItems(["None"] + templates)
            self.template_choice.SetSelection(0)
        
        dlg.Destroy()
    
    def on_upload_audio(self, event):
        # Check if PyAudio is available
        if not PYAUDIO_AVAILABLE:
            wx.MessageBox("PyAudio is not available. Recording functionality will be limited.", 
                         "PyAudio Missing", wx.OK | wx.ICON_WARNING)
        
        # File dialog to select audio file - fix wildcard and dialog settings
        wildcard = "Audio files (*.mp3;*.wav;*.m4a)|*.mp3;*.wav;*.m4a|All files (*.*)|*.*"
        with wx.FileDialog(
            self, 
            message="Choose an audio file",
            defaultDir=os.path.expanduser("~"),  # Start in user's home directory
            defaultFile="",
            wildcard=wildcard,
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        ) as file_dialog:
            
            # Show the dialog and check if user clicked OK
            if file_dialog.ShowModal() == wx.ID_CANCEL:
                return  # User cancelled the dialog
            
            # Get the selected file path
            audio_path = file_dialog.GetPath()
            self.last_audio_path = audio_path  # Store for potential retry
            
            # Show a message that we're processing
            wx.MessageBox(f"Selected file: {audio_path}\n\nStarting transcription...", 
                         "Transcription Started", wx.OK | wx.ICON_INFORMATION)
            
            # Disable UI during processing
            self.notebook.Disable()
            self.status_bar.SetStatusText(f"Transcribing audio...")
            
            # Start transcription in a thread
            threading.Thread(target=self.transcribe_audio, args=(audio_path,), daemon=True).start()
    
    def transcribe_audio(self, audio_path):
        if not self.client:
            wx.CallAfter(self.show_error, "OpenAI API key not set. Please set it in Settings.")
            wx.CallAfter(self.notebook.Enable)
            wx.CallAfter(self.status_bar.SetStatusText, "Error: API key not set")
            return
        
        try:
            # Step 1: Transcribe audio using OpenAI Whisper
            language_display = "English" if self.language == "en" else "Hungarian"
            wx.CallAfter(self.status_bar.SetStatusText, f"Transcribing audio with Whisper in {language_display}...")
            
            with open(audio_path, "rb") as audio_file:
                # Send to OpenAI for transcription
                response = self.client.audio.transcriptions.create(
                    file=audio_file,
                    model="whisper-1",
                    language=self.language,  # Use selected language (en or hu)
                    response_format="verbose_json",
                    timestamp_granularities=["word", "segment"]
                )
            
            # Get basic transcript
            self.transcript = response.text
            self.speakers = []
            
            # Step 2: Perform speaker diarization if available
            if DIARIZATION_AVAILABLE:
                wx.CallAfter(self.status_bar.SetStatusText, "Analyzing speakers...")
                
                try:
                    # Check if HuggingFace token exists in environment
                    hf_token = self.hf_token
                    
                    if not hf_token:
                        # Ask for HuggingFace token if not present
                        self.show_hf_token_dialog()
                        return
                    
                    # Load the speaker diarization pipeline
                    # Speaker diarization works independently of language
                    diarization_pipeline = Pipeline.from_pretrained(
                        "pyannote/speaker-diarization-3.0",
                        use_auth_token=hf_token
                    )
                    
                    # Run the diarization pipeline on the audio file
                    diarization = diarization_pipeline(audio_path)
                    
                    # Process diarization results
                    speaker_segments = {}
                    
                    # Extract speaker segments from diarization
                    for turn, _, speaker in diarization.itertracks(yield_label=True):
                        if speaker not in self.speakers:
                            self.speakers.append(speaker)
                            speaker_segments[speaker] = []
                        
                        speaker_segments[speaker].append((turn.start, turn.end))
                    
                    # Initialize speaker names with default values - use localized naming
                    if self.language == "hu":
                        speaker_prefix = "Beszélő"  # Hungarian for "Speaker"
                    else:
                        speaker_prefix = "Speaker"
                        
                    self.speaker_names = {speaker: f"{speaker_prefix} {i+1}" for i, speaker in enumerate(self.speakers)}
                    
                    # Step 3: Combine transcription with speaker information
                    formatted_transcript = self.combine_transcript_with_speakers(response, speaker_segments)
                    self.transcript = formatted_transcript
                    
                except Exception as e:
                    wx.CallAfter(self.show_error, f"Error during speaker diarization: {str(e)}\nFalling back to basic transcription.")
                    self._fallback_speaker_detection()
            else:
                # If diarization is not available, use basic speaker detection
                self._fallback_speaker_detection()
            
            # Update UI
            wx.CallAfter(self.update_transcript_display)
            wx.CallAfter(self.update_speaker_list)
            wx.CallAfter(self.notebook.Enable)
            wx.CallAfter(self.notebook.SetSelection, 1)  # Switch to transcription tab
            wx.CallAfter(self.status_bar.SetStatusText, "Transcription complete")
            
        except Exception as e:
            wx.CallAfter(self.show_error, f"Error transcribing audio: {str(e)}")
            wx.CallAfter(self.notebook.Enable)
            wx.CallAfter(self.status_bar.SetStatusText, "Error")
    
    def _fallback_speaker_detection(self):
        """Use a basic approach to detect speakers when diarization is not available"""
        paragraphs = self.transcript.split("\n\n")
        speaker_count = min(len(paragraphs), 3)
        
        self.speakers = []
        self.speaker_names = {}
        
        # Use language-appropriate speaker names
        if self.language == "hu":
            speaker_prefix = "Beszélő"  # Hungarian for "Speaker"
        else:
            speaker_prefix = "Speaker"
            
        for i in range(speaker_count):
            speaker_id = f"{speaker_prefix} {i+1}"
            self.speakers.append(speaker_id)
            self.speaker_names[speaker_id] = speaker_id
    
    def combine_transcript_with_speakers(self, whisper_response, speaker_segments):
        """
        Combine the word-level transcription from Whisper with speaker information from diarization.
        
        Args:
            whisper_response: The response from Whisper API with timestamps
            speaker_segments: Dictionary of speaker segments {speaker_id: [(start_time, end_time), ...]}
            
        Returns:
            Formatted transcript with speaker labels
        """
        try:
            # Get words with timestamps from Whisper response
            segments = whisper_response.segments
            
            # Build a new transcript with speaker information
            formatted_lines = []
            current_speaker = None
            current_line = []
            
            for segment in segments:
                for word_info in segment.words:
                    word = word_info.word
                    start_time = word_info.start
                    
                    # Find which speaker was talking at this time
                    speaker_at_time = None
                    for speaker, time_segments in speaker_segments.items():
                        for start, end in time_segments:
                            if start <= start_time <= end:
                                speaker_at_time = speaker
                                break
                        if speaker_at_time:
                            break
                    
                    # If no speaker found or couldn't determine, use the first speaker
                    if not speaker_at_time and self.speakers:
                        speaker_at_time = self.speakers[0]
                    
                    # Start a new line if the speaker changes
                    if speaker_at_time != current_speaker:
                        if current_line:
                            formatted_lines.append(f"{self.speaker_names.get(current_speaker, 'Unknown')}: {' '.join(current_line)}")
                            current_line = []
                        current_speaker = speaker_at_time
                    
                    # Add the word to the current line
                    current_line.append(word)
            
            # Add the last line
            if current_line:
                formatted_lines.append(f"{self.speaker_names.get(current_speaker, 'Unknown')}: {' '.join(current_line)}")
            
            return "\n\n".join(formatted_lines)
            
        except Exception as e:
            print(f"Error combining transcript with speakers: {e}")
            return whisper_response.text  # Fall back to the original transcript
    
    def show_hf_token_dialog(self):
        # Localize dialog text based on language
        if self.language == "hu":
            dialog_title = "HuggingFace Token Szükséges"
            dialog_message = "Kérjük, add meg a HuggingFace hozzáférési tokened a beszélők azonosításához:\n" \
                            "(Szerezz egyet innen: https://huggingface.co/settings/tokens)"
            error_message = "A HuggingFace token szükséges a beszélők azonosításához."
        else:
            dialog_title = "HuggingFace Token Required"
            dialog_message = "Please enter your HuggingFace Access Token for speaker identification:\n" \
                            "(You can get one from https://huggingface.co/settings/tokens)"
            error_message = "HuggingFace token is required for speaker identification."
        
        dialog = wx.TextEntryDialog(
            self, 
            dialog_message,
            dialog_title
        )
        
        if dialog.ShowModal() == wx.ID_OK:
            self.hf_token = dialog.GetValue().strip()
            if self.hf_token:
                # Save the token to environment
                os.environ["HF_TOKEN"] = self.hf_token
                
                # Retry transcription
                self.notebook.Disable()
                self.status_bar.SetStatusText("Retrying transcription...")
                threading.Thread(target=self.transcribe_audio, args=(self.last_audio_path,), daemon=True).start()
            else:
                self.show_error(error_message)
                self.notebook.Enable()
        else:
            self.show_error(error_message)
            self.notebook.Enable()
        
        dialog.Destroy()
    
    def update_transcript_display(self):
        self.transcription_display.Clear()
        
        # For now, just display the transcript
        # In a real implementation, you'd format it with speaker names
        self.transcription_display.SetValue(self.transcript)
    
    def update_speaker_list(self):
        self.speaker_list.DeleteAllItems()
        
        for i, speaker in enumerate(self.speakers):
            index = self.speaker_list.InsertItem(i, speaker)
            self.speaker_list.SetItem(index, 1, self.speaker_names.get(speaker, speaker))
    
    def on_rename_speaker(self, event):
        # Get selected speaker
        selected = self.speaker_list.GetFirstSelected()
        if selected == -1:
            self.show_error("Please select a speaker to rename")
            return
        
        speaker_id = self.speaker_list.GetItemText(selected, 0)
        current_name = self.speaker_list.GetItemText(selected, 1)
        
        # Show dialog to get new name
        dialog = wx.TextEntryDialog(self, f"Enter new name for {speaker_id}:", "Rename Speaker", value=current_name)
        if dialog.ShowModal() == wx.ID_OK:
            new_name = dialog.GetValue().strip()
            if new_name:
                # Update speaker name
                self.speaker_names[speaker_id] = new_name
                self.speaker_list.SetItem(selected, 1, new_name)
        dialog.Destroy()
    
    def on_regenerate_transcript(self, event):
        if not self.transcript or not self.speakers:
            self.show_error("No transcript available to regenerate")
            return
        
        # In a real implementation, you would regenerate the transcript with proper speaker names
        # For now, let's just simulate it by replacing "Speaker X" with the assigned names
        new_transcript = self.transcript
        for speaker_id, name in self.speaker_names.items():
            if speaker_id != name:  # Only replace if name has been changed
                new_transcript = new_transcript.replace(speaker_id, name)
        
        self.transcript = new_transcript
        self.update_transcript_display()
        self.status_bar.SetStatusText("Transcript regenerated with speaker names")
    
    def on_summarize(self, event):
        """Generate a summary of the transcript."""
        if not self.audio_processor.transcript:
            wx.MessageBox("Please transcribe an audio file first.", "No Transcript", wx.OK | wx.ICON_INFORMATION)
            return
            
        # Get selected template
        template_idx = self.template_choice.GetSelection()
        template_name = None
        if template_idx > 0:  # 0 is "None"
            template_name = self.template_choice.GetString(template_idx)
            
        # Disable button during processing
        self.summarize_btn.Disable()
        
        # Start summarization in a separate thread
        transcript = self.transcript_text.GetValue()
        threading.Thread(target=self.summarize_thread, args=(transcript, template_name)).start()
        
    def summarize_thread(self, transcript, template_name):
        """Thread function for transcript summarization."""
        try:
            summary = self.llm_processor.summarize_transcript(transcript, template_name)
            
            # Show summary in a dialog
            wx.CallAfter(self.show_summary_dialog, summary)
        except Exception as e:
            wx.CallAfter(wx.MessageBox, f"Summarization error: {str(e)}", "Error", wx.OK | wx.ICON_ERROR)
        finally:
            wx.CallAfter(self.summarize_btn.Enable)
            
    def show_summary_dialog(self, summary):
        """Show summary in a dialog."""
        dlg = wx.Dialog(self, title="Summary", size=(600, 400))
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        text_ctrl = wx.TextCtrl(dlg, style=wx.TE_MULTILINE | wx.TE_READONLY)
        text_ctrl.SetValue(summary)
        
        sizer.Add(text_ctrl, 1, wx.EXPAND | wx.ALL, 10)
        
        # Add Close button
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        close_btn = wx.Button(dlg, wx.ID_CLOSE)
        btn_sizer.Add(close_btn, 0, wx.ALL, 5)
        
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        
        dlg.SetSizer(sizer)
        
        close_btn.Bind(wx.EVT_BUTTON, lambda event: dlg.EndModal(wx.ID_CLOSE))
        
        dlg.ShowModal()
        dlg.Destroy()
        
    def update_button_states(self):
        """Update the enabled/disabled states of buttons based on current state."""
        has_audio_file = bool(self.audio_file_path.GetValue())
        has_transcript = hasattr(self.audio_processor, 'transcript') and bool(self.audio_processor.transcript)
        has_speakers = hasattr(self.audio_processor, 'speakers') and bool(self.audio_processor.speakers)
        
        if hasattr(self, 'transcribe_btn'):
            self.transcribe_btn.Enable(has_audio_file)
            
        if hasattr(self, 'identify_speakers_btn'):
            self.identify_speakers_btn.Enable(has_transcript)
            
        if hasattr(self, 'apply_speaker_names_btn'):
            self.apply_speaker_names_btn.Enable(has_speakers)
            
        if hasattr(self, 'summarize_btn'):
            self.summarize_btn.Enable(has_transcript)
    
    def on_upload_document(self, event):
        # Improved file dialog to select document
        wildcard = "Text files (*.txt)|*.txt|PDF files (*.pdf)|*.pdf|All files (*.*)|*.*"
        with wx.FileDialog(
            self, 
            message="Choose a document to add",
            defaultDir=os.path.expanduser("~"),  # Start in user's home directory
            defaultFile="",
            wildcard=wildcard,
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        ) as file_dialog:
            
            # Show the dialog and check if user clicked OK
            if file_dialog.ShowModal() == wx.ID_CANCEL:
                return  # User cancelled the dialog
            
            # Get the selected file path
            doc_path = file_dialog.GetPath()
            filename = os.path.basename(doc_path)
            dest_path = os.path.join(self.documents_folder, filename)
            
            # Check if file already exists
            if os.path.exists(dest_path):
                dialog = wx.MessageDialog(self, f"File {filename} already exists. Replace it?",
                                         "File exists", wx.YES_NO | wx.ICON_QUESTION)
                if dialog.ShowModal() == wx.ID_NO:
                    dialog.Destroy()
                    return
                dialog.Destroy()
            
            # Copy file to documents folder
            try:
                shutil.copy2(doc_path, dest_path)
                self.status_bar.SetStatusText(f"Document {filename} uploaded")
                
                # Show success message
                wx.MessageBox(f"Document '{filename}' has been successfully added.", 
                             "Document Added", wx.OK | wx.ICON_INFORMATION)
            except Exception as e:
                self.show_error(f"Error uploading document: {str(e)}")
    
    def on_select_documents(self, event):
        # Get list of documents
        try:
            files = os.listdir(self.documents_folder)
            files = [f for f in files if os.path.isfile(os.path.join(self.documents_folder, f))]
        except Exception as e:
            self.show_error(f"Error listing documents: {str(e)}")
            return
        
        if not files:
            self.show_error("No documents found. Please upload documents first.")
            return
        
        # Create a dialog with checkboxes for each document
        dialog = wx.Dialog(self, title="Select Documents", size=(400, 300))
        panel = wx.Panel(dialog)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Instruction text
        instructions = wx.StaticText(panel, label="Select documents to load into context:")
        sizer.Add(instructions, flag=wx.ALL, border=10)
        
        # Checkboxes for each document
        checkboxes = {}
        for filename in files:
            checkbox = wx.CheckBox(panel, label=filename)
            checkbox.SetValue(filename in self.loaded_documents)
            checkboxes[filename] = checkbox
            sizer.Add(checkbox, flag=wx.ALL, border=5)
        
        # Buttons
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        ok_button = wx.Button(panel, wx.ID_OK, "OK")
        cancel_button = wx.Button(panel, wx.ID_CANCEL, "Cancel")
        
        button_sizer.Add(ok_button, flag=wx.RIGHT, border=5)
        button_sizer.Add(cancel_button)
        
        sizer.Add(button_sizer, flag=wx.ALIGN_RIGHT | wx.ALL, border=10)
        
        panel.SetSizer(sizer)
        
        # Show dialog
        if dialog.ShowModal() == wx.ID_OK:
            # Load selected documents
            selected = [filename for filename, checkbox in checkboxes.items() if checkbox.GetValue()]
            
            # Clear previously loaded documents
            self.loaded_documents = {}
            
            # Load new selections
            for filename in selected:
                try:
                    with open(os.path.join(self.documents_folder, filename), 'r', encoding='utf-8') as f:
                        self.loaded_documents[filename] = f.read()
                except Exception as e:
                    self.show_error(f"Error loading {filename}: {str(e)}")
            
            self.status_bar.SetStatusText(f"Loaded {len(self.loaded_documents)} documents")
        
        dialog.Destroy()
    
    def on_settings(self, event):
        # Switch to the Settings tab
        self.notebook.SetSelection(2)  # Index 2 is the Settings tab
    
    def on_exit(self, event):
        self.Close()
    
    def on_about(self, event):
        info = wx.adv.AboutDialogInfo()
        info.SetName("AI Assistant")
        info.SetVersion("1.0")
        info.SetDescription("An AI assistant application for transcription, summarization, and document processing.")
        info.SetCopyright("(C) 2023")
        
        wx.adv.AboutBox(info)
    
    def show_error(self, message):
        wx.MessageBox(message, "Error", wx.OK | wx.ICON_ERROR)

    def on_save_settings(self, event):
        """Save settings from the Settings tab"""
        # Save API keys
        new_api_key = self.openai_input.GetValue().strip()
        new_hf_token = self.hf_input.GetValue().strip()
        
        # Get language selection
        lang_selection = self.lang_combo.GetSelection()
        if lang_selection == 1:  # Hungarian
            new_language = "hu"
        else:  # Default to English
            new_language = "en"
        
        # Update OpenAI API Key if changed
        if new_api_key != self.api_key:
            self.api_key = new_api_key
            os.environ["OPENAI_API_KEY"] = self.api_key
            
            # Update client
            if self.api_key:
                try:
                    self.client = OpenAI(api_key=self.api_key)
                except Exception as e:
                    self.show_error(f"Error setting OpenAI API key: {e}")
        
        # Update HuggingFace token if changed
        if new_hf_token != self.hf_token:
            self.hf_token = new_hf_token
            os.environ["HF_TOKEN"] = self.hf_token
        
        # Update language if changed
        if new_language != self.language:
            self.language = new_language
            os.environ["TRANSCRIPTION_LANGUAGE"] = self.language
        
        self.status_bar.SetStatusText("Settings saved successfully")

    def _identify_speakers_chunked(self, paragraphs, chunk_size):
        """Process long transcripts in chunks for speaker identification."""
        self.update_status("Processing transcript in chunks...", percent=0.1)
        
        # Group paragraphs into chunks
        chunks = []
        current_chunk = []
        current_length = 0
        
        for p in paragraphs:
            if current_length + len(p) > chunk_size and current_chunk:
                chunks.append(current_chunk)
                current_chunk = [p]
                current_length = len(p)
            else:
                current_chunk.append(p)
                current_length += len(p)
                
        # Add the last chunk
        if current_chunk:
            chunks.append(current_chunk)
            
        self.update_status(f"Processing transcript in {len(chunks)} chunks...", percent=0.15)
        
        # Process first chunk to establish speaker patterns
        model_to_use = DEFAULT_OPENAI_MODEL
        
        # Initialize result container
        all_results = []
        speaker_characteristics = {}
        
        # Process each chunk
        for i, chunk in enumerate(chunks):
            # Calculate progress percentage (0-1)
            progress = (i / len(chunks)) * 0.7 + 0.2  # 20% to 90% of total progress
            
            self.update_status(f"Processing chunk {i+1}/{len(chunks)}...", percent=progress)
            
            # For first chunk, get detailed analysis
            if i == 0:
                prompt = f"""
                Analyze this transcript segment and identify exactly two speakers (A and B).
                
                TASK:
                1. Determine which paragraphs belong to which speaker
                2. Identify each speaker's characteristics and speaking style
                3. Ensure logical conversation flow
                
                Return JSON in this exact format:
                {{
                    "analysis": {{
                        "speaker_a_characteristics": ["characteristic 1", "characteristic 2"],
                        "speaker_b_characteristics": ["characteristic 1", "characteristic 2"]
                    }},
                    "paragraphs": [
                        {{
                            "id": {len(all_results)},
                            "speaker": "A",
                            "text": "paragraph text"
                        }},
                        ...
                    ]
                }}
                
                Transcript paragraphs:
                {json.dumps([{"id": len(all_results) + j, "text": p} for j, p in enumerate(chunk)])}
                """
            else:
                # For subsequent chunks, use characteristics from first analysis
                prompt = f"""
                Continue assigning speakers to this transcript segment.
                
                Speaker A characteristics: {json.dumps(speaker_characteristics.get("speaker_a_characteristics", []))}
                Speaker B characteristics: {json.dumps(speaker_characteristics.get("speaker_b_characteristics", []))}
                
                Return JSON with speaker assignments:
                {{
                    "paragraphs": [
                        {{
                            "id": {len(all_results)},
                            "speaker": "A or B",
                            "text": "paragraph text"
                        }},
                        ...
                    ]
                }}
                
                Transcript paragraphs:
                {json.dumps([{"id": len(all_results) + j, "text": p} for j, p in enumerate(chunk)])}
                """
            
            # Make API call for this chunk
            response = self.client.chat.completions.create(
                model=model_to_use,
                messages=[
                    {"role": "system", "content": "You are an expert conversation analyst who identifies speaker turns in transcripts with high accuracy."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Save speaker characteristics from first chunk
            if i == 0 and "analysis" in result:
                speaker_characteristics = result["analysis"]
            
            # Add results from this chunk
            if "paragraphs" in result:
                all_results.extend(result["paragraphs"])
            
            # Update progress
            after_progress = (i + 0.5) / len(chunks) * 0.7 + 0.2
            self.update_status(f"Processed chunk {i+1}/{len(chunks)}...", percent=after_progress)
        
        # Map Speaker A/B to Speaker 1/2
        speaker_map = {
            "A": "Speaker 1", 
            "B": "Speaker 2",
            "Speaker A": "Speaker 1", 
            "Speaker B": "Speaker 2"
        }
        
        self.update_status("Finalizing speaker assignments...", percent=0.95)
        
        # Create final speakers list
        self.speakers = []
        for item in sorted(all_results, key=lambda x: x.get("id", 0)):
            speaker_label = item.get("speaker", "Unknown")
            mapped_speaker = speaker_map.get(speaker_label, speaker_label)
            
            self.speakers.append({
                "speaker": mapped_speaker,
                "text": item.get("text", "")
            })
        
        # Ensure we have the right number of paragraphs
        if len(self.speakers) != len(paragraphs):
            self.update_status(f"Warning: Received {len(self.speakers)} segments but expected {len(paragraphs)}. Fixing...", percent=0.98)
            self.speakers = [
                {"speaker": self.speakers[min(i, len(self.speakers)-1)]["speaker"] if self.speakers else f"Speaker {i % 2 + 1}", 
                 "text": p}
                for i, p in enumerate(paragraphs)
            ]
        
        self.update_status(f"Speaker identification complete. Found 2 speakers across {len(chunks)} chunks.", percent=1.0)
        return self.speakers

    def identify_speakers_simple(self, transcript):
        """Identify speakers using a simplified and optimized approach."""
        self.update_status("Analyzing transcript for speaker identification...", percent=0.1)
        
        # First, split transcript into paragraphs
        paragraphs = self._create_improved_paragraphs(transcript)
        self.speaker_segments = paragraphs
        
        # Setup model
        model_to_use = DEFAULT_OPENAI_MODEL
        
        # For very long transcripts, we'll analyze in chunks
        MAX_CHUNK_SIZE = 8000  # characters per chunk
        
        if len(transcript) > MAX_CHUNK_SIZE:
            self.update_status("Long transcript detected. Processing in chunks...", percent=0.15)
            return self._identify_speakers_chunked(paragraphs, MAX_CHUNK_SIZE)
        
        # Enhanced single-pass approach for shorter transcripts
        prompt = f"""
        Analyze this transcript and identify exactly two speakers (A and B).
        
        TASK:
        1. Determine which paragraphs belong to which speaker
        2. Focus on conversation pattern and speaking style
        3. Ensure logical conversation flow (e.g., questions are followed by answers)
        4. Maintain consistency in first-person statements
        
        Return JSON in this exact format:
        {{
            "analysis": {{
                "speaker_a_characteristics": ["characteristic 1", "characteristic 2"],
                "speaker_b_characteristics": ["characteristic 1", "characteristic 2"],
                "speaker_count": 2,
                "conversation_type": "interview/discussion/etc"
            }},
            "paragraphs": [
                {{
                    "id": 0,
                    "speaker": "A",
                    "text": "paragraph text"
                }},
                ...
            ]
        }}
        
        Transcript paragraphs:
        {json.dumps([{"id": i, "text": p} for i, p in enumerate(paragraphs)])}
        """
        
        try:
            # Single API call to assign speakers
            self.update_status("Sending transcript for speaker analysis...", percent=0.3)
            response = self.client.chat.completions.create(
                model=model_to_use,
                messages=[
                    {"role": "system", "content": "You are an expert conversation analyst who identifies speaker turns in transcripts with high accuracy."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            
            self.update_status("Processing speaker identification results...", percent=0.7)
            result = json.loads(response.choices[0].message.content)
            
            # Get paragraph assignments
            assignments = result.get("paragraphs", [])
            
            # Map Speaker A/B to Speaker 1/2 for compatibility with existing system
            speaker_map = {
                "A": "Speaker 1", 
                "B": "Speaker 2",
                "Speaker A": "Speaker 1", 
                "Speaker B": "Speaker 2"
            }
            
            # Create speakers list with proper mapping
            self.speakers = []
            for item in sorted(assignments, key=lambda x: x.get("id", 0)):
                speaker_label = item.get("speaker", "Unknown")
                mapped_speaker = speaker_map.get(speaker_label, speaker_label)
                
                self.speakers.append({
                    "speaker": mapped_speaker,
                    "text": item.get("text", "")
                })
            
            # Ensure we have the right number of paragraphs
            if len(self.speakers) != len(paragraphs):
                self.update_status(f"Warning: Received {len(self.speakers)} segments but expected {len(paragraphs)}. Fixing...", percent=0.9)
                self.speakers = [
                    {"speaker": self.speakers[min(i, len(self.speakers)-1)]["speaker"] if self.speakers else f"Speaker {i % 2 + 1}", 
                     "text": p}
                    for i, p in enumerate(paragraphs)
                ]
            
            self.update_status(f"Speaker identification complete. Found {2} speakers.", percent=1.0)
            return self.speakers
            
        except Exception as e:
            self.update_status(f"Error in speaker identification: {str(e)}", percent=0)
            # Fallback to basic alternating speaker assignment
            self.speakers = [
                {"speaker": f"Speaker {i % 2 + 1}", "text": p}
                for i, p in enumerate(paragraphs)
            ]
            return self.speakers
            
    def _create_improved_paragraphs(self, transcript):
        """Create more intelligent paragraph breaks based on semantic analysis."""
        import re
        # Split transcript into sentences
        sentences = re.split(r'(?<=[.!?])\s+', transcript.strip())
        sentences = [s.strip() for s in sentences if s.strip()]
        
        # Group sentences into paragraphs
        paragraphs = []
        current_para = []
        
        # These phrases often signal the start of a new speaker's turn
        new_speaker_indicators = [
            "yes", "no", "I think", "I believe", "so,", "well,", "actually", 
            "to be honest", "in my opinion", "I agree", "I disagree",
            "let me", "I'd like to", "I would", "you know", "um", "uh", 
            "hmm", "but", "however", "from my perspective", "wait", "okay",
            "right", "sure", "exactly", "absolutely", "definitely", "perhaps",
            "look", "listen", "basically", "frankly", "honestly", "now", "so",
            "thank you", "thanks", "good point", "interesting", "true", "correct",
            "first of all", "firstly", "secondly", "finally", "in conclusion"
        ]
        
        # Words/phrases that indicate continuation by the same speaker
        continuation_indicators = [
            "and", "also", "additionally", "moreover", "furthermore", "plus",
            "then", "after that", "next", "finally", "lastly", "in addition",
            "consequently", "as a result", "therefore", "thus", "besides",
            "for example", "specifically", "in particular", "especially",
            "because", "since", "due to", "as such", "which means"
        ]
        
        for i, sentence in enumerate(sentences):
            # Start a new paragraph if:
            start_new_para = False
            
            # 1. This is the first sentence
            if i == 0:
                start_new_para = True
                
            # 2. Previous sentence ended with a question mark
            elif i > 0 and sentences[i-1].endswith('?'):
                start_new_para = True
                
            # 3. Current sentence begins with a common new speaker phrase
            elif any(sentence.lower().startswith(indicator.lower()) for indicator in new_speaker_indicators):
                start_new_para = True
                
            # 4. Not a continuation and not a pronoun reference
            elif (i > 0 and 
                  not any(sentence.lower().startswith(indicator.lower()) for indicator in continuation_indicators) and
                  not re.match(r'^(It|This|That|These|Those|They|He|She|We|I)\b', sentence, re.IGNORECASE) and
                  len(current_para) >= 2):
                start_new_para = True
                
            # 5. Natural length limit to avoid overly long paragraphs
            elif len(current_para) >= 4:
                start_new_para = True
            
            # Start a new paragraph if needed
            if start_new_para and current_para:
                paragraphs.append(' '.join(current_para))
                current_para = []
            
            current_para.append(sentence)
        
        # Add the last paragraph
        if current_para:
            paragraphs.append(' '.join(current_para))
        
        return paragraphs

    def assign_speaker_names(self, speaker_map):
        """Apply custom speaker names to the transcript."""
        if not hasattr(self, 'speakers') or not self.speakers:
            return self.transcript
            
        # Create a formatted transcript with the new speaker names
        formatted_text = []
        
        for segment in self.speakers:
            original_speaker = segment.get("speaker", "Unknown")
            new_speaker = speaker_map.get(original_speaker, original_speaker)
            text = segment.get("text", "")
            
            formatted_text.append(f"{new_speaker}: {text}")
            
        return "\n\n".join(formatted_text)

    def create_audio_panel(self):
        """Create the audio processing panel."""
        panel = self.audio_panel
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # File upload section
        file_box = wx.StaticBox(panel, label="Audio File")
        file_sizer = wx.StaticBoxSizer(file_box, wx.VERTICAL)
        
        file_select_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.audio_file_path = wx.TextCtrl(panel, style=wx.TE_READONLY)
        browse_btn = wx.Button(panel, label="Browse")
        browse_btn.Bind(wx.EVT_BUTTON, self.on_browse_audio)
        
        file_select_sizer.Add(self.audio_file_path, proportion=1, flag=wx.EXPAND | wx.RIGHT, border=5)
        file_select_sizer.Add(browse_btn, proportion=0, flag=wx.EXPAND)
        
        file_sizer.Add(file_select_sizer, 1, wx.EXPAND | wx.ALL, 5)
        
        sizer.Add(file_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # Create transcription controls
        transcribe_box = wx.StaticBox(panel, label="Transcription")
        transcribe_sizer = wx.StaticBoxSizer(transcribe_box, wx.VERTICAL)
        
        # Language selector
        lang_sizer = wx.BoxSizer(wx.HORIZONTAL)
        lang_label = wx.StaticText(panel, label="Language:")
        self.language_choice = wx.Choice(panel, choices=["English", "Hungarian"])
        self.language_choice.SetSelection(0 if self.config_manager.get_language() == "english" else 1)
        
        lang_sizer.Add(lang_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        lang_sizer.Add(self.language_choice, 1, wx.EXPAND)
        
        transcribe_sizer.Add(lang_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # Transcribe button
        self.transcribe_btn = wx.Button(panel, label="Transcribe Audio")
        self.transcribe_btn.Bind(wx.EVT_BUTTON, self.on_transcribe)
        self.transcribe_btn.Disable()  # Start disabled
        transcribe_sizer.Add(self.transcribe_btn, 0, wx.EXPAND | wx.ALL, 5)
        
        sizer.Add(transcribe_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # Speaker identification
        speaker_box = wx.StaticBox(panel, label="Speaker Identification")
        speaker_sizer = wx.StaticBoxSizer(speaker_box, wx.VERTICAL)
        
        self.identify_speakers_btn = wx.Button(panel, label=self.get_speaker_id_button_label())
        self.identify_speakers_btn.Bind(wx.EVT_BUTTON, self.on_identify_speakers)
        self.identify_speakers_btn.Disable()  # Start disabled
        
        # Set button styling based on PyAnnote availability
        self.update_speaker_id_button_style()
        
        speaker_sizer.Add(self.identify_speakers_btn, 0, wx.EXPAND | wx.ALL, 5)
        
        # Add help text
        self.speaker_id_help_text = wx.StaticText(panel, label=self.get_speaker_id_help_text())
        self.speaker_id_help_text.SetForegroundColour(wx.Colour(100, 100, 100))  # Gray text
        speaker_sizer.Add(self.speaker_id_help_text, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
        
        sizer.Add(speaker_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # Transcript display
        transcript_box = wx.StaticBox(panel, label="Transcript")
        transcript_sizer = wx.StaticBoxSizer(transcript_box, wx.VERTICAL)
        
        self.transcript_text = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        self.transcript_text.SetMinSize((400, 200))
        transcript_sizer.Add(self.transcript_text, 1, wx.EXPAND | wx.ALL, 5)
        
        # Speaker list
        speaker_list_box = wx.StaticBox(panel, label="Speakers")
        speaker_list_sizer = wx.StaticBoxSizer(speaker_list_box, wx.VERTICAL)
        
        self.speaker_list = wx.ListCtrl(panel, style=wx.LC_REPORT)
        self.speaker_list.InsertColumn(0, "ID", width=50)
        self.speaker_list.InsertColumn(1, "Name", width=150)
        speaker_list_sizer.Add(self.speaker_list, 1, wx.EXPAND | wx.ALL, 5)
        
        # Edit speakers button
        rename_speaker_btn = wx.Button(panel, label="Rename Speaker")
        rename_speaker_btn.Bind(wx.EVT_BUTTON, self.on_rename_speaker)
        speaker_list_sizer.Add(rename_speaker_btn, 0, wx.EXPAND | wx.ALL, 5)
        
        # Create a horizontal sizer for transcript and speaker list
        transcript_speaker_sizer = wx.BoxSizer(wx.HORIZONTAL)
        transcript_speaker_sizer.Add(transcript_sizer, 2, wx.EXPAND | wx.RIGHT, 5)
        transcript_speaker_sizer.Add(speaker_list_sizer, 1, wx.EXPAND)
        
        sizer.Add(transcript_speaker_sizer, 1, wx.EXPAND | wx.ALL, 5)
        
        # Summarization section
        summary_box = wx.StaticBox(panel, label="Summarization")
        summary_sizer = wx.StaticBoxSizer(summary_box, wx.VERTICAL)
        
        # Template selection
        template_sizer = wx.BoxSizer(wx.HORIZONTAL)
        template_label = wx.StaticText(panel, label="Template:")
        
        # Get templates from config
        template_names = list(self.config_manager.get_templates().keys())
        self.template_choice = wx.Choice(panel, choices=["None"] + template_names)
        self.template_choice.SetSelection(0)
        self.template_choice.Bind(wx.EVT_CHOICE, self.on_template_selected)
        
        template_sizer.Add(template_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        template_sizer.Add(self.template_choice, 1, wx.EXPAND)
        
        summary_sizer.Add(template_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # Summarize button
        self.summarize_btn = wx.Button(panel, label="Summarize Transcript")
        self.summarize_btn.Bind(wx.EVT_BUTTON, self.on_summarize)
        self.summarize_btn.Disable()  # Start disabled
        summary_sizer.Add(self.summarize_btn, 0, wx.EXPAND | wx.ALL, 5)
        
        sizer.Add(summary_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        panel.SetSizer(sizer)
        
        return panel

    def bind_events(self):
        """Bind events to handlers."""
        # Enter key in prompt input
        if hasattr(self, 'prompt_input'):
            self.prompt_input.Bind(wx.EVT_TEXT_ENTER, self.on_send_prompt)
        
    def on_close(self, event):
        """Handle application close event."""
        self.Destroy()
        
    def update_status(self, message, percent=None):
        """Update status bar with message and optional progress percentage."""
        if percent is not None:
            self.status_bar.SetStatusText(f"{message} ({percent:.0f}%)")
        else:
            self.status_bar.SetStatusText(message)
            
    def on_identify_speakers(self, event):
        """Handle speaker identification button click."""
        if hasattr(self, 'transcript') and self.transcript:
            has_token = bool(self.config_manager.get_pyannote_token())
            if has_token and hasattr(self, 'last_audio_path') and self.last_audio_path:
                # Use advanced speaker identification with diarization
                threading.Thread(
                    target=self.identify_speakers_with_diarization,
                    args=(self.last_audio_path, self.transcript),
                    daemon=True
                ).start()
            else:
                # Use basic speaker identification
                self.identify_speakers_simple(self.transcript)
        else:
            wx.MessageBox("No transcript available. Please transcribe audio first.", 
                         "No Transcript", wx.OK | wx.ICON_INFORMATION)
    
    def on_browse_audio(self, event):
        """Handle audio file browse button."""
        wildcard = (
            "Audio files|*.flac;*.m4a;*.mp3;*.mp4;*.mpeg;*.mpga;*.oga;*.ogg;*.wav;*.webm|"
            "FLAC files (*.flac)|*.flac|"
            "M4A files (*.m4a)|*.m4a|"
            "MP3 files (*.mp3)|*.mp3|"
            "MP4 files (*.mp4)|*.mp4|"
            "OGG files (*.ogg;*.oga)|*.ogg;*.oga|"
            "WAV files (*.wav)|*.wav|"
            "All files (*.*)|*.*"
        )
        
        with wx.FileDialog(self, "Choose an audio file", wildcard=wildcard,
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as file_dialog:
            if file_dialog.ShowModal() == wx.ID_CANCEL:
                return
                
            path = file_dialog.GetPath()
            
            # Validate file extension
            file_ext = os.path.splitext(path)[1].lower()
            supported_formats = ['.flac', '.m4a', '.mp3', '.mp4', '.mpeg', '.mpga', '.oga', '.ogg', '.wav', '.webm']
            
            if file_ext not in supported_formats:
                # If user selected "All files" and chose an unsupported format
                wx.MessageBox(
                    f"The selected file has an unsupported format: {file_ext}\n"
                    f"Supported formats are: {', '.join(supported_formats)}", 
                    "Unsupported Format", 
                    wx.OK | wx.ICON_WARNING
                )
                return
                
            # Check file size
            file_size_mb = os.path.getsize(path) / (1024 * 1024)
            if file_size_mb > 25:
                wx.MessageBox(
                    f"The selected file is {file_size_mb:.1f}MB, which exceeds the 25MB limit for OpenAI's Whisper API.\n"
                    f"Please choose a smaller file or compress this one.",
                    "File Too Large",
                    wx.OK | wx.ICON_WARNING
                )
                return
                
            self.audio_file_path.SetValue(path)
            self.update_status(f"Selected audio file: {os.path.basename(path)} ({file_size_mb:.1f}MB)", percent=0)
            self.update_button_states()
            
    def on_transcribe(self, event):
        """Handle audio transcription."""
        if not self.audio_file_path.GetValue():
            wx.MessageBox("Please select an audio file first.", "No File Selected", wx.OK | wx.ICON_INFORMATION)
            return
            
        # Check if API key is set
        if not self.config_manager.get_api_key():
            wx.MessageBox("Please set your OpenAI API key in the Settings tab.", "API Key Required", wx.OK | wx.ICON_INFORMATION)
            return
            
        # Get language
        lang_map = {"English": "en", "Hungarian": "hu"}
        lang_selection = self.language_choice.GetString(self.language_choice.GetSelection())
        language = lang_map.get(lang_selection, "en")
        
        # Save language choice to config
        self.config_manager.set_language("english" if language == "en" else "hungarian")
        
        # Store the audio file path in the AudioProcessor
        # This ensures it's available for diarization later
        self.audio_processor.audio_file_path = self.audio_file_path.GetValue()
        
        # Update status message
        self.update_status(f"Transcribing in {lang_selection}...", percent=0)
        
        # Disable buttons during processing
        self.transcribe_btn.Disable()
        self.identify_speakers_btn.Disable()
        self.summarize_btn.Disable()
        
        # Start transcription in a separate thread
        threading.Thread(target=self.transcribe_thread, args=(self.audio_file_path.GetValue(), language)).start()
        
    def transcribe_thread(self, file_path, language):
        """Thread function for audio transcription."""
        try:
            # Get file extension for better error reporting
            file_ext = os.path.splitext(file_path)[1].lower()
            
            response = self.audio_processor.transcribe_audio(file_path, language)
            
            # Add a note about speaker identification at the top of the transcript
            transcription_notice = "--- TRANSCRIPTION COMPLETE ---\n" + \
                                  "To identify speakers in this transcript, click the 'Identify Speakers' button below.\n\n"
            
            wx.CallAfter(self.transcript_text.SetValue, transcription_notice + self.audio_processor.transcript)
            wx.CallAfter(self.update_button_states)
            wx.CallAfter(self.update_status, f"Transcription complete: {len(self.audio_processor.transcript)} characters", percent=100)
            
            # Show a dialog informing the user to use speaker identification
            wx.CallAfter(self.show_speaker_id_hint)
            
        except FileNotFoundError as e:
            wx.CallAfter(wx.MessageBox, f"File not found: {str(e)}", "Error", wx.OK | wx.ICON_ERROR)
        except ValueError as e:
            error_msg = str(e)
            title = "Format Error"
            
            # Special handling for common error cases
            if 'ffprobe' in error_msg or 'ffmpeg' in error_msg:
                title = "FFmpeg Missing"
                error_msg = error_msg.replace('[Errno 2] No such file or directory:', 'Missing required component:')
                # Installation instructions are already in the error message from _get_ffmpeg_install_instructions
            elif file_ext == '.m4a' and 'Invalid file format' in error_msg:
                error_msg = (
                    "There was an issue with your M4A file. Some M4A files have compatibility issues with the OpenAI API.\n\n"
                    "Possible solutions:\n"
                    "1. Install FFmpeg on your system (required for m4a processing)\n"
                    "2. Convert the file to WAV or MP3 format manually\n"
                    "3. Try a different M4A file (some are more compatible than others)"
                )
                title = "M4A Compatibility Issue"
                
            wx.CallAfter(wx.MessageBox, error_msg, title, wx.OK | wx.ICON_ERROR)
        except openai.RateLimitError:
            wx.CallAfter(wx.MessageBox, "OpenAI rate limit exceeded. Please try again later.", "Rate Limit Error", wx.OK | wx.ICON_ERROR)
        except openai.AuthenticationError:
            wx.CallAfter(wx.MessageBox, "Authentication error. Please check your OpenAI API key in the Settings tab.", "Authentication Error", wx.OK | wx.ICON_ERROR)
        except openai.BadRequestError as e:
            error_msg = str(e)
            title = "API Error"
            
            if "Invalid file format" in error_msg and file_ext == '.m4a':
                error_msg = (
                    "Your M4A file format is not compatible with the OpenAI API.\n\n"
                    "Possible solutions:\n"
                    "1. Install FFmpeg on your system (required for m4a processing)\n"
                    "2. Convert the file to WAV or MP3 format manually\n"
                    "3. Try a different M4A file (some are more compatible than others)"
                )
                title = "M4A Format Error"
                
            wx.CallAfter(wx.MessageBox, error_msg, title, wx.OK | wx.ICON_ERROR)
        except Exception as e:
            error_msg = str(e)
            if 'ffprobe' in error_msg or 'ffmpeg' in error_msg:
                # Handle FFmpeg-related errors not caught by previous handlers
                install_instructions = self.audio_processor._get_ffmpeg_install_instructions()
                error_msg = f"FFmpeg/FFprobe is required but not found. Please install it to process audio files.\n\n{install_instructions}"
                wx.CallAfter(wx.MessageBox, error_msg, "FFmpeg Required", wx.OK | wx.ICON_ERROR)
            else:
                wx.CallAfter(wx.MessageBox, f"Transcription error: {error_msg}", "Error", wx.OK | wx.ICON_ERROR)
        finally:
            wx.CallAfter(self.transcribe_btn.Enable)
            wx.CallAfter(self.update_status, "Ready", percent=0)
            
    def show_speaker_id_hint(self):
        """Show a hint dialog about using speaker identification."""
        # Check if PyAnnote is available
        if PYANNOTE_AVAILABLE:
            message = (
                "Transcription is complete!\n\n"
                "To identify different speakers in this transcript, click the 'Identify Speakers' button.\n\n"
                "This system will use advanced audio-based speaker diarization to detect different "
                "speakers by analyzing voice characteristics (pitch, tone, speaking style) from the "
                "original audio file.\n\n"
                "This approach is significantly more accurate than text-based analysis since it "
                "uses the actual voice patterns to distinguish between speakers."
            )
        else:
            message = (
                "Transcription is complete!\n\n"
                "To identify different speakers in this transcript, click the 'Identify Speakers' button.\n\n"
                "Currently, the system will analyze the text patterns to detect different speakers.\n\n"
                "For more accurate speaker identification, consider installing PyAnnote which uses "
                "audio analysis to distinguish speakers based on their voice characteristics. "
                "Click 'Yes' for installation instructions."
            )
            
        dlg = wx.MessageDialog(
            self,
            message,
            "Speaker Identification",
            wx.OK | (wx.CANCEL | wx.YES_NO if not PYANNOTE_AVAILABLE else wx.OK) | wx.ICON_INFORMATION
        )
        
        result = dlg.ShowModal()
        dlg.Destroy()
        
        # If user wants to install PyAnnote
        if result == wx.ID_YES:
            self.show_pyannote_setup_guide()
        
        # Highlight the identify speakers button
        self.identify_speakers_btn.SetFocus()

    def show_format_info(self):
        """Show information about supported audio formats."""
        ffmpeg_missing = not self._is_ffmpeg_available()
        pydub_missing = not PYDUB_AVAILABLE
        
        if ffmpeg_missing or pydub_missing:
            needed_tools = []
            if pydub_missing:
                needed_tools.append("pydub (pip install pydub)")
            if ffmpeg_missing:
                needed_tools.append("FFmpeg")
                
            # Get platform-specific installation instructions
            ffmpeg_install = self.audio_processor._get_ffmpeg_install_instructions() if hasattr(self, 'audio_processor') else ""
            
            msg = (
                "For better audio file compatibility, especially with M4A files, "
                f"you need to install the following tools:\n\n{', '.join(needed_tools)}\n\n"
            )
            
            if ffmpeg_missing:
                msg += f"FFmpeg installation instructions:\n{ffmpeg_install}\n\n"
                msg += "FFmpeg is required for processing M4A files. Without it, M4A transcription will likely fail."
            
            self.update_status("FFmpeg required for M4A support - please install it", percent=0)
            
            # Always show FFmpeg warning because it's critical
            if ffmpeg_missing:
                wx.MessageBox(msg, "FFmpeg Required for M4A Files", wx.OK | wx.ICON_WARNING)
                self.config_manager.config["shown_format_info"] = True
                self.config_manager.save_config()
            # Only show other warnings if not shown before
            elif not self.config_manager.config.get("shown_format_info", False):
                wx.MessageBox(msg, "Audio Format Information", wx.OK | wx.ICON_INFORMATION)
                self.config_manager.config["shown_format_info"] = True
                self.config_manager.save_config()

    def _is_ffmpeg_available(self):
        """Check if ffmpeg is available on the system."""
        try:
            subprocess.run(
                ["ffmpeg", "-version"], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                check=True
            )
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def check_pyannote(self):
        """Check if PyAnnote is available and show installation instructions if not."""
        if not PYANNOTE_AVAILABLE:
            dlg = wx.MessageDialog(
                self,
                "PyAnnote is not installed. PyAnnote provides more accurate speaker diarization "
                "by analyzing audio directly, rather than just text.\n\n"
                "To install PyAnnote and set it up, click 'Yes' for detailed instructions.",
                "Speaker Diarization Enhancement",
                wx.YES_NO | wx.ICON_INFORMATION
            )
            if dlg.ShowModal() == wx.ID_YES:
                self.show_pyannote_setup_guide()
            dlg.Destroy()
    
    def show_pyannote_setup_guide(self):
        """Show detailed setup instructions for PyAnnote."""
        dlg = wx.Dialog(self, title="PyAnnote Setup Guide", size=(650, 550))
        
        panel = wx.Panel(dlg)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Create a styled text control for better formatting
        text = wx.TextCtrl(
            panel, 
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
            size=(-1, 400)
        )
        
        # Set up the instructions
        guide = """PYANNOTE SETUP GUIDE

Step 1: Install Required Dependencies
--------------------------------------
Run the following commands in your terminal:

pip install torch torchaudio
pip install pyannote.audio

Step 2: Get HuggingFace Access Token
------------------------------------
1. Create a HuggingFace account at https://huggingface.co/join
2. Go to https://huggingface.co/pyannote/speaker-diarization
3. Accept the user agreement
4. Go to https://huggingface.co/settings/tokens
5. Create a new token with READ access
6. Copy the token

Step 3: Configure the Application
--------------------------------
1. After installing, restart this application
2. Go to the Settings tab
3. Paste your token in the "PyAnnote Speaker Diarization" section
4. Click "Save Token"
5. Return to the Audio Processing tab
6. Click "Identify Speakers" to use audio-based speaker identification

Important Notes:
---------------
• PyAnnote requires at least 4GB of RAM
• GPU acceleration (if available) will make processing much faster
• For best results, use high-quality audio with minimal background noise
• The first run may take longer as models are downloaded

Troubleshooting:
---------------
• If you get CUDA errors, try installing a compatible PyTorch version for your GPU
• If you get "Access Denied" errors, check that your token is valid and you've accepted the license agreement
• For long audio files (>10 min), processing may take several minutes
"""
        
        # Add the text with some styling
        text.SetValue(guide)
        
        # Style the headers
        text.SetStyle(0, 19, wx.TextAttr(wx.BLUE, wx.NullColour, wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)))
        
        # Find all the section headers and style them
        for section in ["Step 1:", "Step 2:", "Step 3:", "Important Notes:", "Troubleshooting:"]:
            start = guide.find(section)
            if start != -1:
                end = start + len(section)
                text.SetStyle(start, end, wx.TextAttr(wx.Colour(128, 0, 128), wx.NullColour, wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)))
        
        # Add to sizer
        sizer.Add(text, 1, wx.EXPAND | wx.ALL, 10)
        
        # Add buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # Add a button to copy installation commands
        copy_btn = wx.Button(panel, label="Copy Installation Commands")
        copy_btn.Bind(wx.EVT_BUTTON, lambda e: self.copy_to_clipboard("pip install torch torchaudio\npip install pyannote.audio"))
        btn_sizer.Add(copy_btn, 0, wx.RIGHT, 10)
        
        # Add a button to open HuggingFace token page
        hf_btn = wx.Button(panel, label="Open HuggingFace Token Page")
        hf_btn.Bind(wx.EVT_BUTTON, lambda e: wx.LaunchDefaultBrowser("https://huggingface.co/settings/tokens"))
        btn_sizer.Add(hf_btn, 0, wx.RIGHT, 10)
        
        # Add button to go to settings tab
        settings_btn = wx.Button(panel, label="Go to Settings Tab")
        settings_btn.Bind(wx.EVT_BUTTON, lambda e: (self.notebook.SetSelection(2), dlg.EndModal(wx.ID_CLOSE)))
        btn_sizer.Add(settings_btn, 0, wx.RIGHT, 10)
        
        # Add close button
        close_btn = wx.Button(panel, wx.ID_CLOSE)
        close_btn.Bind(wx.EVT_BUTTON, lambda e: dlg.EndModal(wx.ID_CLOSE))
        btn_sizer.Add(close_btn, 0)
        
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        
        panel.SetSizer(sizer)
        dlg.ShowModal()
        dlg.Destroy()
    
    def copy_to_clipboard(self, text):
        """Copy text to clipboard."""
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(text))
            wx.TheClipboard.Close()
            wx.MessageBox("Commands copied to clipboard", "Copied", wx.OK | wx.ICON_INFORMATION)

    def on_template_selected(self, event):
        """Handle selection of a template."""
        selected = self.template_list.GetSelection()
        if selected == wx.NOT_FOUND:
            return
            
        template_name = self.template_list.GetString(selected)
        templates = self.config_manager.get_templates()
        
        if template_name in templates:
            self.template_content_input.SetValue(templates[template_name])
        else:
            self.template_content_input.Clear()

    def _quick_consistency_check(self):
        """Ultra-quick consistency check for short files"""
        if len(self.speakers) < 3:
            return
            
        # Look for isolated speaker segments
        for i in range(1, len(self.speakers) - 1):
            prev_speaker = self.speakers[i-1]["speaker"]
            curr_speaker = self.speakers[i]["speaker"]
            next_speaker = self.speakers[i+1]["speaker"]
            
            # If current speaker is sandwiched between different speakers
            if prev_speaker == next_speaker and curr_speaker != prev_speaker:
                # Fix the segment only if very short (likely error)
                if len(self.speakers[i]["text"].split()) < 15:
                    self.speakers[i]["speaker"] = prev_speaker

    def _process_audio_in_chunks(self, pipeline, audio_file, total_duration, chunk_size):
        """Process long audio files in chunks to optimize memory usage and speed."""
        from pyannote.core import Segment, Annotation
        import concurrent.futures
        from threading import Lock
        
        # Initialize a combined annotation object
        combined_diarization = Annotation()
        
        # Calculate number of chunks
        num_chunks = int(np.ceil(total_duration / chunk_size))
        self.update_status(f"Processing audio in {num_chunks} chunks...", percent=0.1)
        
        # Optimize number of workers based on file length and available memory
        # More chunks = more workers (up to cpu_count), but limit for very long files
        # to avoid excessive memory usage
        cpu_count = os.cpu_count() or 4
        
        try:
            # Create hash of file path and modification time to use as cache key
            file_stats = os.stat(audio_file_path)
            file_hash = hashlib.md5(f"{audio_file_path}_{file_stats.st_mtime}".encode()).hexdigest()
            
            # Use APP_BASE_DIR if available
            if APP_BASE_DIR:
                cache_dir = os.path.join(APP_BASE_DIR, "diarization_cache")
            else:
                cache_dir = "diarization_cache"
                
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir)
                
            # Cache file path
            cache_file = os.path.join(cache_dir, f"{file_hash}.diar")
            
            # Save results
            self.update_status("Saving diarization results to cache for future use...", percent=0.95)
            with open(cache_file, 'wb') as f:
                pickle.dump(self.diarization, f)
            
            # Clean up old cache files if there are more than 20
            cache_files = [os.path.join(cache_dir, f) for f in os.listdir(cache_dir) if f.endswith('.diar')]
            if len(cache_files) > 20:
                # Sort by modification time and remove oldest
                cache_files.sort(key=os.path.getmtime)
                for old_file in cache_files[:-20]:  # Keep the 20 most recent
                    os.unlink(old_file)
                    
            self.update_status("Successfully cached results for future use", percent=0.98)
        except Exception as e:
            self.update_status(f"Error saving to cache: {str(e)}", percent=0.95)
            # Continue without caching - non-critical error
    
    def identify_speakers_with_diarization(self, audio_file_path, transcript):
        """Identify speakers using audio diarization with PyAnnote."""
        self.update_status("Performing audio diarization analysis...", percent=0.05)
        
        # Check if PyAnnote is available
        if not PYANNOTE_AVAILABLE:
            self.update_status("PyAnnote not available. Install with: pip install pyannote.audio", percent=0)
            return self.identify_speakers_simple(transcript)
        
        # Check if we have cached results - if so, skip to mapping
        if self._check_diarization_cache(audio_file_path):
            self.update_status("Using cached diarization results...", percent=0.4)
            
            # Get audio information for status reporting
            audio_duration = librosa.get_duration(path=audio_file_path)
            is_short_file = audio_duration < 300
            
            # Skip to mapping step
            if is_short_file:
                self.update_status("Fast mapping diarization to transcript...", percent=0.8)
                return self._fast_map_diarization(transcript)
            else:
                return self._map_diarization_to_transcript(transcript)
        
        # No cache, proceed with normal processing
        # Step 1: Initialize PyAnnote pipeline
        try:
            # Get token from config_manager if available
            token = None
            if self.config_manager:
                token = self.config_manager.get_pyannote_token()
            
            # If not found, check for a token file as a fallback
            if not token:
                # Use APP_BASE_DIR if available
                if APP_BASE_DIR:
                    token_file = os.path.join(APP_BASE_DIR, "pyannote_token.txt")
                else:
                    token_file = "pyannote_token.txt"
                
                if os.path.exists(token_file):
                    with open(token_file, "r") as f:
                        file_token = f.read().strip()
                        if not file_token.startswith("#") and len(file_token) >= 10:
                            token = file_token
            
            # If still no token, show message and fall back to text-based identification
            if not token:
                self.update_status("PyAnnote token not found in settings. Please add your token in the Settings tab.", percent=0)
                return self.identify_speakers_simple(transcript)
            
            self.update_status("Initializing diarization pipeline...", percent=0.1)
            
            # Initialize the PyAnnote pipeline
            pipeline = pyannote.audio.Pipeline.from_pretrained(
                "pyannote/speaker-diarization@2.1",
                use_auth_token=token
            )
            
            # Set device (GPU if available)
            device = "cuda" if torch.cuda.is_available() else "cpu"
            pipeline = pipeline.to(torch.device(device))
            
            # Convert the file to WAV format if needed
            if not audio_file_path.lower().endswith('.wav'):
                self.update_status("Converting audio to WAV format for diarization...", percent=0.15)
                converted_file = self.convert_to_wav(audio_file_path)
                diarization_file = converted_file
            else:
                diarization_file = audio_file_path
            
            # Get audio file information
            audio_duration = librosa.get_duration(path=diarization_file)
            self.update_status(f"Audio duration: {audio_duration:.1f} seconds", percent=0.2)
            
            # Very short files need very different processing approach
            is_short_file = audio_duration < 300  # Less than 5 minutes
            
            if is_short_file:
                # Ultra fast mode for short files (5 min or less) - direct processing with optimized parameters
                self.update_status("Short audio detected, using ultra-fast mode...", percent=0.25)
                
                # Use ultra-optimized parameters for short files
                pipeline.instantiate({
                    # More aggressive voice activity detection for speed
                    "segmentation": {
                        "min_duration_on": 0.25,      # Shorter minimum speech (default 0.1s)
                        "min_duration_off": 0.25,     # Shorter minimum silence (default 0.1s)
                    },
                    # Faster clustering with fewer speakers expected in short clips
                    "clustering": {
                        "min_cluster_size": 6,        # Require fewer samples (default 15)
                        "method": "centroid"          # Faster than "average" linkage
                    },
                    # Skip post-processing for speed
                    "segmentation_batch_size": 32,    # Larger batch for speed
                    "embedding_batch_size": 32,       # Larger batch for speed
                })
                
                # Apply diarization directly for short files
                self.update_status("Processing audio (fast mode)...", percent=0.3)
                self.diarization = pipeline(diarization_file)
                
                # For very short files, optimize the diarization results
                if audio_duration < 60:  # Less than 1 minute
                    # Further optimize by limiting max speakers for very short clips
                    num_speakers = len(set(s for _, _, s in self.diarization.itertracks(yield_label=True)))
                    if num_speakers > 3:
                        self.update_status("Optimizing speaker count for short clip...", percent=0.7)
                        # Re-run with max_speakers=3 for very short clips
                        self.diarization = pipeline(diarization_file, num_speakers=3)
            else:
                # Determine chunk size based on audio duration - longer files use chunking
                if audio_duration > 10800:  # > 3 hours
                    # For extremely long recordings, use very small 3-minute chunks
                    MAX_CHUNK_DURATION = 180  # 3 minutes per chunk
                    self.update_status("Extremely long audio detected (>3 hours). Using highly optimized micro-chunks.", percent=0.22)
                elif audio_duration > 5400:  # > 1.5 hours
                    # For very long recordings, use 4-minute chunks
                    MAX_CHUNK_DURATION = 240  # 4 minutes per chunk
                    self.update_status("Very long audio detected (>1.5 hours). Using micro-chunks for improved performance.", percent=0.22)
                elif audio_duration > 3600:  # > 1 hour
                    # For long recordings, use 5-minute chunks
                    MAX_CHUNK_DURATION = 300  # 5 minutes per chunk
                    self.update_status("Long audio detected (>1 hour). Using optimized chunk size.", percent=0.22)
                elif audio_duration > 1800:  # > 30 minutes
                    # For medium recordings, use 7.5-minute chunks
                    MAX_CHUNK_DURATION = 450  # 7.5 minutes per chunk
                    self.update_status("Medium-length audio detected (>30 minutes). Using optimized chunk size.", percent=0.22)
                else:
                    # Default 10-minute chunks for shorter files
                    MAX_CHUNK_DURATION = 600  # 10 minutes per chunk
                
                # Process in chunks for longer files
                self.update_status("Processing in chunks for optimized performance...", percent=0.25)
                self.diarization = self._process_audio_in_chunks(pipeline, diarization_file, audio_duration, MAX_CHUNK_DURATION)
            
            # Clean up converted file if needed
            if diarization_file != audio_file_path and os.path.exists(diarization_file):
                os.unlink(diarization_file)
            
            # Save diarization results to cache for future use
            self._save_diarization_cache(audio_file_path)
            
            # Now we have diarization data, map it to the transcript using word timestamps
            # Use optimized mapping for short files
            if is_short_file:
                self.update_status("Fast mapping diarization to transcript...", percent=0.8)
                return self._fast_map_diarization(transcript)
            else:
                return self._map_diarization_to_transcript(transcript)
            
        except Exception as e:
            self.update_status(f"Error in diarization: {str(e)}", percent=0)
            # Fall back to text-based approach
            return self.identify_speakers_simple(transcript)

    def _fast_map_diarization(self, transcript):
        """Simplified and faster mapping for short files."""
        self.update_status("Fast mapping diarization results to transcript...", percent=0.85)
        
        if not hasattr(self, 'word_by_word') or not self.word_by_word or not self.diarization:
            return self.identify_speakers_simple(transcript)
        
        try:
            # Create speaker timeline map at higher granularity (every 0.2s)
            timeline_map = {}
            speaker_set = set()
            
            # Extract all speakers and their time ranges
            for segment, _, speaker in self.diarization.itertracks(yield_label=True):
                start_time = segment.start
                end_time = segment.end
                speaker_set.add(speaker)
                
                # For short files, we can afford fine-grained sampling
                step = 0.1  # 100ms steps
                for t in np.arange(start_time, end_time, step):
                    timeline_map[round(t, 1)] = speaker
            
            # Create paragraphs if they don't exist
            if hasattr(self, 'speaker_segments') and self.speaker_segments:
                paragraphs = self.speaker_segments
            else:
                paragraphs = self._create_improved_paragraphs(transcript)
                self.speaker_segments = paragraphs
            
            # Calculate overall speakers - short clips typically have 1-3 speakers
            num_speakers = len(speaker_set)
            self.update_status(f"Detected {num_speakers} speakers in audio", percent=0.9)
            
            # Map each word to a speaker
            word_speakers = {}
            for word_info in self.word_by_word:
                if not hasattr(word_info, "start") or not hasattr(word_info, "end"):
                    continue
                
                # Take the middle point of each word
                word_time = round((word_info.start + word_info.end) / 2, 1)
                
                # Find closest time in our map
                closest_time = min(timeline_map.keys(), key=lambda x: abs(x - word_time), default=None)
                if closest_time is not None and abs(closest_time - word_time) < 1.0:
                    word_speakers[word_info.word] = timeline_map[closest_time]
            
            # Now assign speakers to paragraphs based on word majority
            self.speakers = []
            for paragraph in paragraphs:
                para_speakers = []
                
                # Count speakers in this paragraph
                words = re.findall(r'\b\w+\b', paragraph.lower())
                for word in words:
                    if word in word_speakers:
                        para_speakers.append(word_speakers[word])
                
                # Find most common speaker
                if para_speakers:
                    from collections import Counter
                    speaker_counts = Counter(para_speakers)
                    most_common_speaker = speaker_counts.most_common(1)[0][0]
                    speaker_id = f"Speaker {most_common_speaker.split('_')[-1]}"
                else:
                    # Fallback for paragraphs with no identified speaker
                    speaker_id = f"Speaker 1"
                
                self.speakers.append({
                    "speaker": speaker_id,
                    "text": paragraph
                })
            
            # Final quick consistency check for short files
            if len(self.speakers) > 1:
                self._quick_consistency_check()
            
            self.update_status(f"Diarization complete. Found {num_speakers} speakers.", percent=1.0)
            return self.speakers
            
        except Exception as e:
            self.update_status(f"Error in fast mapping: {str(e)}", percent=0)
            return self.identify_speakers_simple(transcript)
    
    def _map_diarization_to_transcript(self, transcript):
        """Memory-efficient mapping for long files by using sparse sampling and batch processing."""
        self.update_status("Mapping diarization results to transcript (optimized for long files)...", percent=0.8)
        
        if not hasattr(self, 'word_by_word') or not self.word_by_word or not self.diarization:
            return self.identify_speakers_simple(transcript)
            
        try:
            # Get initial speaker count for progress reporting
            speaker_set = set()
            segment_count = 0
            
            # Quick scan to count speakers and segments - don't store details yet
            for segment, _, speaker in self.diarization.itertracks(yield_label=True):
                speaker_set.add(speaker)
                segment_count += 1
                
            num_speakers = len(speaker_set)
            self.update_status(f"Detected {num_speakers} speakers across {segment_count} segments", percent=0.82)
            
            # Create paragraphs if they don't exist
            if hasattr(self, 'speaker_segments') and self.speaker_segments:
                paragraphs = self.speaker_segments
            else:
                paragraphs = self._create_improved_paragraphs(transcript)
                self.speaker_segments = paragraphs
                
            # OPTIMIZATION 1: For long files, use sparse sampling of the timeline
            # Instead of creating a dense timeline map which is memory-intensive,
            # we'll create a sparse map with only the segment boundaries
            timeline_segments = []
            
            # Use diarization_cache directory for temporary storage if needed
            if APP_BASE_DIR:
                cache_dir = os.path.join(APP_BASE_DIR, "diarization_cache")
            else:
                cache_dir = "diarization_cache"
                
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir)
                
            # OPTIMIZATION 2: For very long files, process diarization in chunks to avoid memory issues
            chunk_size = 1000  # Process 1000 segments at a time
            use_temp_storage = segment_count > 5000  # Only use temp storage for very large files
            
            # If using temp storage, save intermediate results to avoid memory buildup
            if use_temp_storage:
                self.update_status("Using temporary storage for large diarization data...", percent=0.83)
                temp_file = os.path.join(cache_dir, f"diarization_map_{int(time.time())}.json")
                
                # Process in chunks to avoid memory buildup
                processed = 0
                segment_chunk = []
                
                for segment, _, speaker in self.diarization.itertracks(yield_label=True):
                    # Skip very short segments
                    if segment.duration < 0.5:
                        continue
                        
                    segment_chunk.append({
                        "start": segment.start,
                        "end": segment.end,
                        "speaker": speaker
                    })
                    
                    processed += 1
                    
                    # When chunk is full, process it
                    if len(segment_chunk) >= chunk_size:
                        timeline_segments.extend(segment_chunk)
                        # Save intermediate results
                        with open(temp_file, 'w') as f:
                            json.dump(timeline_segments, f)
                        # Clear memory
                        timeline_segments = []
                        segment_chunk = []
                        # Update progress
                        progress = 0.83 + (processed / segment_count) * 0.05
                        self.update_status(f"Processed {processed}/{segment_count} diarization segments...", percent=progress)
                
                # Process remaining segments
                if segment_chunk:
                    timeline_segments.extend(segment_chunk)
                    with open(temp_file, 'w') as f:
                        json.dump(timeline_segments, f)
                
                # Load from file to continue processing
                with open(temp_file, 'r') as f:
                    timeline_segments = json.load(f)
            else:
                # For smaller files, process all at once
                for segment, _, speaker in self.diarization.itertracks(yield_label=True):
                    # Skip very short segments
                    if segment.duration < 0.5:
                        continue
                        
                    timeline_segments.append({
                        "start": segment.start,
                        "end": segment.end,
                        "speaker": speaker
                    })
            
            self.update_status("Matching words to speaker segments...", percent=0.89)
            
            # OPTIMIZATION 3: Optimize word-to-speaker mapping for long files
            # Sort segments by start time for faster searching
            timeline_segments.sort(key=lambda x: x["start"])
            
            # Initialize paragraph mapping structures
            paragraph_speaker_counts = [{} for _ in paragraphs]
            
            # Batch process words to reduce computation
            batch_size = 500
            num_words = len(self.word_by_word)
            
            # Calculate which paragraph each word belongs to
            word_paragraphs = {}
            
            para_start_idx = 0
            for i, word_info in enumerate(self.word_by_word):
                if not hasattr(word_info, "start") or not hasattr(word_info, "end"):
                    continue
                    
                # Binary search to find the paragraph for this word
                # This is much faster than iterating through all paragraphs for each word
                word = word_info.word.lower()
                
                # Find paragraph for this word only once
                if i % 100 == 0:  # Only update progress occasionally
                    progress = 0.89 + (i / num_words) * 0.05
                    self.update_status(f"Matching words to paragraphs ({i}/{num_words})...", percent=progress)
                
                # Find which paragraph this word belongs to
                found_para = False
                for p_idx in range(para_start_idx, len(paragraphs)):
                    if word in paragraphs[p_idx].lower():
                        word_paragraphs[word] = p_idx
                        para_start_idx = p_idx  # Optimization: start next search from here
                        found_para = True
                        break
                
                if not found_para:
                    # If we didn't find it moving forward, try searching all paragraphs
                    for p_idx in range(len(paragraphs)):
                        if word in paragraphs[p_idx].lower():
                            word_paragraphs[word] = p_idx
                            para_start_idx = p_idx
                            found_para = True
                            break
            
            # Process words in batches to assign speakers efficiently
            for batch_start in range(0, num_words, batch_size):
                batch_end = min(batch_start + batch_size, num_words)
                
                for i in range(batch_start, batch_end):
                    if i >= len(self.word_by_word):
                        break
                        
                    word_info = self.word_by_word[i]
                    if not hasattr(word_info, "start") or not hasattr(word_info, "end"):
                        continue
                    
                    word = word_info.word.lower()
                    word_time = (word_info.start + word_info.end) / 2
                    
                    # Find segment for this word using binary search for speed
                    left, right = 0, len(timeline_segments) - 1
                    segment_idx = -1
                    
                    while left <= right:
                        mid = (left + right) // 2
                        if timeline_segments[mid]["start"] <= word_time <= timeline_segments[mid]["end"]:
                            segment_idx = mid
                            break
                        elif word_time < timeline_segments[mid]["start"]:
                            right = mid - 1
                        else:
                            left = mid + 1
                    
                    # If we found a segment, update the paragraph speaker counts
                    if segment_idx != -1:
                        speaker = timeline_segments[segment_idx]["speaker"]
                        
                        # If we know which paragraph this word belongs to, update its speaker count
                        if word in word_paragraphs:
                            para_idx = word_paragraphs[word]
                            paragraph_speaker_counts[para_idx][speaker] = paragraph_speaker_counts[para_idx].get(speaker, 0) + 1
                
                # Update progress
                progress = 0.94 + (batch_end / num_words) * 0.05
                self.update_status(f"Processed {batch_end}/{num_words} words...", percent=progress)
            
            # Assign speakers to paragraphs based on majority vote
            self.speakers = []
            for i, paragraph in enumerate(paragraphs):
                # Get speaker counts for this paragraph
                speaker_counts = paragraph_speaker_counts[i]
                
                # Assign the most common speaker, or default if none
                if speaker_counts:
                    # Find speaker with highest count
                    most_common_speaker = max(speaker_counts.items(), key=lambda x: x[1])[0]
                    speaker_id = f"Speaker {most_common_speaker.split('_')[-1]}"
                else:
                    # Default speaker if no match found
                    speaker_id = f"Speaker 1"
                
                self.speakers.append({
                    "speaker": speaker_id,
                    "text": paragraph
                })
            
            # Quick consistency check
            if len(self.speakers) > 2:
                self._quick_consistency_check()
            
            # Clean up temp file if used
            if use_temp_storage and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except:
                    pass
            
            self.update_status(f"Diarization mapping complete. Found {num_speakers} speakers.", percent=1.0)
            return self.speakers
            
        except Exception as e:
            self.update_status(f"Error in diarization mapping: {str(e)}", percent=0)
            # Fall back to text-based approach
            return self.identify_speakers_simple(transcript)

    def create_chat_panel(self):
        """Create the chat panel."""
        # Main sizer for chat panel
        chat_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Chat history
        history_label = wx.StaticText(self.chat_panel, label="Chat History:")
        self.chat_history_text = wx.TextCtrl(self.chat_panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        
        # User input area
        input_label = wx.StaticText(self.chat_panel, label="Your Message:")
        self.user_input = wx.TextCtrl(self.chat_panel, style=wx.TE_MULTILINE)
        
        # Buttons
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        send_button = wx.Button(self.chat_panel, label="Send")
        clear_button = wx.Button(self.chat_panel, label="Clear History")
        
        button_sizer.Add(send_button, 0, wx.ALL, 5)
        button_sizer.Add(clear_button, 0, wx.ALL, 5)
        
        chat_sizer.Add(history_label, 0, wx.ALL, 5)
        chat_sizer.Add(self.chat_history_text, 1, wx.EXPAND | wx.ALL, 5)
        chat_sizer.Add(input_label, 0, wx.ALL, 5)
        chat_sizer.Add(self.user_input, 0, wx.EXPAND | wx.ALL, 5)
        chat_sizer.Add(button_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        self.chat_panel.SetSizer(chat_sizer)
        
    def create_settings_panel(self):
        """Create the settings panel."""
        settings_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # API Key input
        api_label = wx.StaticText(self.settings_panel, label="OpenAI API Key:")
        self.api_key_input = wx.TextCtrl(self.settings_panel, style=wx.TE_PASSWORD)
        
        # PyAnnote Token input
        pyannote_label = wx.StaticText(self.settings_panel, label="PyAnnote Token:")
        self.pyannote_token_input = wx.TextCtrl(self.settings_panel, style=wx.TE_PASSWORD)
        
        # Model selection
        model_label = wx.StaticText(self.settings_panel, label="Model:")
        self.model_choice = wx.Choice(self.settings_panel, choices=["gpt-4o", "gpt-3.5-turbo"])
        
        # Temperature slider
        temp_label = wx.StaticText(self.settings_panel, label="Temperature:")
        self.temperature_slider = wx.Slider(self.settings_panel, minValue=0, maxValue=100, value=70)
        
        # Language selection
        language_label = wx.StaticText(self.settings_panel, label="Language:")
        self.language_settings_choice = wx.Choice(self.settings_panel, choices=["English", "Hungarian"])
        
        # Templates selection
        template_label = wx.StaticText(self.settings_panel, label="Templates:")
        self.template_name_input = wx.TextCtrl(self.settings_panel)
        self.template_content_input = wx.TextCtrl(self.settings_panel, style=wx.TE_MULTILINE)
        
        settings_sizer.Add(api_label, 0, wx.ALL, 5)
        settings_sizer.Add(self.api_key_input, 0, wx.EXPAND | wx.ALL, 5)
        settings_sizer.Add(pyannote_label, 0, wx.ALL, 5)
        settings_sizer.Add(self.pyannote_token_input, 0, wx.EXPAND | wx.ALL, 5)
        settings_sizer.Add(model_label, 0, wx.ALL, 5)
        settings_sizer.Add(self.model_choice, 0, wx.EXPAND | wx.ALL, 5)
        settings_sizer.Add(temp_label, 0, wx.ALL, 5)
        settings_sizer.Add(self.temperature_slider, 0, wx.EXPAND | wx.ALL, 5)
        settings_sizer.Add(language_label, 0, wx.ALL, 5)
        settings_sizer.Add(self.language_settings_choice, 0, wx.EXPAND | wx.ALL, 5)
        settings_sizer.Add(template_label, 0, wx.ALL, 5)
        settings_sizer.Add(self.template_name_input, 0, wx.EXPAND | wx.ALL, 5)
        settings_sizer.Add(self.template_content_input, 0, wx.EXPAND | wx.ALL, 5)
        
        self.settings_panel.SetSizer(settings_sizer)
        
    def on_send_prompt(self, event):
        """Handle sending a prompt from the chat input."""
        prompt = self.chat_input.GetValue()
        if prompt.strip():
            self.llm_processor.generate_response(prompt)
            self.chat_input.SetValue("")

# LLM Processing Class
class LLMProcessor:
    def __init__(self, client, config_manager, update_callback=None):
        self.client = client
        self.config_manager = config_manager
        self.update_callback = update_callback
        self.chat_history = []
        
    def update_status(self, message, percent=None):
        if self.update_callback:
            wx.CallAfter(self.update_callback, message, percent)
            
    def generate_response(self, prompt, temperature=None):
        """Generate a response from the LLM."""
        if temperature is None:
            temperature = self.config_manager.get_temperature()
            
        model = self.config_manager.get_model()
        messages = self.prepare_messages(prompt)
        
        try:
            self.update_status("Generating response...", percent=0)
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature
            )
            
            response_text = response.choices[0].message.content
            
            # Add to chat history
            self.chat_history.append({"role": "user", "content": prompt})
            self.chat_history.append({"role": "assistant", "content": response_text})
            
            self.update_status("Response generated.", percent=100)
            return response_text
            
        except Exception as e:
            self.update_status(f"Error generating response: {str(e)}", percent=50)
            return f"Error: {str(e)}"
            
    def prepare_messages(self, prompt):
        """Prepare messages for the LLM, including chat history."""
        messages = []
        
        # Add system message
        system_content = "You are a helpful assistant that can analyze transcripts."
        messages.append({"role": "system", "content": system_content})
        
        # Add chat history (limit to last 10 messages to avoid token limits)
        if self.chat_history:
            messages.extend(self.chat_history[-10:])
            
        # Add the current prompt
        if prompt not in [msg["content"] for msg in messages if msg["role"] == "user"]:
            messages.append({"role": "user", "content": prompt})
            
        return messages
        
    def clear_chat_history(self):
        """Clear the chat history."""
        self.chat_history = []
        self.update_status("Chat history cleared.", percent=0)
        
    def summarize_transcript(self, transcript, template_name=None):
        """Summarize a transcript, optionally using a template."""
        if not transcript:
            return "No transcript to summarize."
            
        self.update_status("Generating summary...", percent=0)
        
        prompt = f"Summarize the following transcript:"
        template = None
        
        if template_name:
            templates = self.config_manager.get_templates()
            if template_name in templates:
                template = templates[template_name]
                prompt += f" Follow this template format:\n\n{template}"
                
        prompt += f"\n\nTranscript:\n{transcript}"
        
        try:
            response = self.client.chat.completions.create(
                model=self.config_manager.get_model(),
                messages=[
                    {"role": "system", "content": "You are an assistant that specializes in summarizing transcripts."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5
            )
            
            summary = response.choices[0].message.content
            
            # Save summary to file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Use APP_BASE_DIR if available
            if APP_BASE_DIR:
                summary_dir = os.path.join(APP_BASE_DIR, "Summaries")
                if not os.path.exists(summary_dir):
                    os.makedirs(summary_dir)
                summary_filename = os.path.join(summary_dir, f"summary_{timestamp}.txt")
            else:
                summary_filename = f"Summaries/summary_{timestamp}.txt"
                
            with open(summary_filename, 'w', encoding='utf-8') as f:
                f.write(summary)
                
            self.update_status(f"Summary generated and saved to {summary_filename}.", percent=100)
            return summary
            
        except Exception as e:
            self.update_status(f"Error generating summary: {str(e)}", percent=50)
            return f"Error: {str(e)}"

class ConfigManager:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.config_file = os.path.join(base_dir, "config.json")
        self.config = self.load_config()
        
    def load_config(self):
        """Load configuration from file, or create default if not exists."""
        default_config = {
            "api_key": "",
            "pyannote_token": "",
            "model": "gpt-4o",
            "temperature": 0.7,
            "language": "en",
            "templates": {
                "Standard Summary": "Please create a concise summary of the following transcript. Identify key points, decisions, and action items if present.",
                "Meeting Notes": "Please analyze this meeting transcript and create structured notes with these sections: 1) Attendees, 2) Key Discussion Points, 3) Decisions Made, 4) Action Items with Owners, 5) Next Steps",
                "Executive Summary": "Create an executive summary of this transcript. Focus on strategic implications, key decisions, and recommendations. Keep it brief but comprehensive."
            }
        }
        
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # Ensure all keys from default config exist
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                    
                    # Special handling for templates to ensure default templates exist
                    if key == "templates" and isinstance(value, dict):
                        for template_name, template_content in value.items():
                            if template_name not in config["templates"]:
                                config["templates"][template_name] = template_content
                
                return config
            else:
                # Create default config
                self.save_config(default_config)
                return default_config
        except Exception as e:
            print(f"Error loading config: {e}")
            return default_config
    
    def save_config(self, config=None):
        """Save configuration to file."""
        if config is None:
            config = self.config
        
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
            
            # Update instance config
            self.config = config
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def get_api_key(self):
        """Get OpenAI API key."""
        return self.config.get("api_key", "")
    
    def set_api_key(self, api_key):
        """Set OpenAI API key."""
        self.config["api_key"] = api_key
        return self.save_config()
    
    def get_pyannote_token(self):
        """Get Hugging Face token for PyAnnote."""
        return self.config.get("pyannote_token", "")
    
    def set_pyannote_token(self, token):
        """Set Hugging Face token for PyAnnote."""
        self.config["pyannote_token"] = token
        return self.save_config()
    
    def get_model(self):
        """Get selected LLM model."""
        return self.config.get("model", "gpt-4o")
    
    def set_model(self, model):
        """Set LLM model."""
        self.config["model"] = model
        return self.save_config()
    
    def get_temperature(self):
        """Get temperature setting."""
        return self.config.get("temperature", 0.7)
    
    def set_temperature(self, temperature):
        """Set temperature."""
        try:
            temperature = float(temperature)
            if 0 <= temperature <= 2:
                self.config["temperature"] = temperature
                return self.save_config()
            return False
        except:
            return False
    
    def get_language(self):
        """Get selected language."""
        return self.config.get("language", "en")
    
    def set_language(self, language):
        """Set language."""
        self.config["language"] = language
        return self.save_config()
    
    def get_templates(self):
        """Get all templates."""
        return self.config.get("templates", {})
    
    def get_template(self, name):
        """Get specific template by name."""
        templates = self.get_templates()
        return templates.get(name, "")
    
    def add_template(self, name, content):
        """Add or update a template."""
        if "templates" not in self.config:
            self.config["templates"] = {}
        
        self.config["templates"][name] = content
        return self.save_config()
    
    def remove_template(self, name):
        """Remove a template."""
        if "templates" in self.config and name in self.config["templates"]:
            del self.config["templates"][name]
            return self.save_config()
        return False

if __name__ == "__main__":
    try:
        print("Starting Audio Processing App...")
        
        # Ensure required directories exist and get base directory
        # Critical step: this must succeed before proceeding
        try:
            APP_BASE_DIR = ensure_directories()
            print(f"Using application directory: {APP_BASE_DIR}")
            
            # Verify directories are created and writable
            for subdir in ["Transcripts", "Summaries", "diarization_cache"]:
                test_dir = os.path.join(APP_BASE_DIR, subdir)
                if not os.path.exists(test_dir):
                    os.makedirs(test_dir, exist_ok=True)
                
                # Verify we can write to the directory
                test_file = os.path.join(test_dir, ".write_test")
                try:
                    with open(test_file, 'w') as f:
                        f.write("test")
                    if os.path.exists(test_file):
                        os.remove(test_file)
                    print(f"Directory {test_dir} is writable")
                except Exception as e:
                    print(f"WARNING: Directory {test_dir} is not writable: {e}")
                    # Try to find an alternative location
                    APP_BASE_DIR = os.path.join(os.path.expanduser("~"), "AudioProcessingApp")
                    os.makedirs(APP_BASE_DIR, exist_ok=True)
                    print(f"Using alternative directory: {APP_BASE_DIR}")
                    break
        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            print(f"FATAL ERROR setting up directories: {error_msg}")
            
            # Use a simple directory in the user's home folder as a last resort
            APP_BASE_DIR = os.path.join(os.path.expanduser("~"), "AudioProcessingApp")
            os.makedirs(APP_BASE_DIR, exist_ok=True)
            print(f"Using fallback directory: {APP_BASE_DIR}")
        
        # Short delay to ensure filesystem operations complete
        import time
        time.sleep(0.5)
        
        # Create and start the application
        app = MainApp()
        app.MainLoop()
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        print(f"FATAL ERROR: {error_msg}")
        
        # Try to show error dialog if possible
        try:
            import wx
            if not hasattr(wx, 'App') or not wx.GetApp():
                error_app = wx.App(False)
            wx.MessageBox(f"Fatal error starting application:\n\n{error_msg}", 
                         "Application Error", wx.OK | wx.ICON_ERROR)
        except:
            # If we can't even show a dialog, just exit
            pass
        
        sys.exit(1) 
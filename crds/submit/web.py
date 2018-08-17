"""This module codifies standard practices for scripted interactions with the 
web server file submission system.
"""
from crds.core import log, utils
from . import background

# from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor
try:
    import requests
    DISABLED = []
except (ImportError, RuntimeError):
    log.verbose_warning("Import of 'requests' failed.  submit disabled.")
    DISABLED.append("requests")
try:
    from lxml import html
except (ImportError, RuntimeError):
    log.verbose_warning("Import of 'lxml' failed.  submit disabled.")
    DISABLED.append("lxml")

# ==================================================================================================

def log_section(section_name, section_value, verbosity=50, log_function=log.verbose, 
                divider_name=None):
    """Issue log divider bar followed by a corresponding log message."""
    log.divider(name=divider_name, verbosity=verbosity, func=log.verbose)
    log_function(section_name, section_value, verbosity=verbosity+5)

# ==================================================================================================

class CrdsDjangoConnection:

    """This class handles CRDS authentication, basic GET, basic POST, and CRDS-style get/post.
    It also manages the CSRF token generated by Django to block form forgeries and CRDS instrument
    management/locking.
    """

    def __init__(self, locked_instrument="none", username=None, password=None, base_url=None):
        if DISABLED:
            log.fatal_error("Missing or broken depenencies:", DISABLED)
        self.locked_instrument = locked_instrument
        self.username = username
        self.password = password
        self.base_url = base_url
        self.session = requests.session()
        self.session.headers.update({'referer': self.base_url})

    def abs_url(self, relative_url):
        """Return the absolute server URL constructed from the given `relative_url`."""
        return self.base_url + relative_url

    def dump_response(self, name, response):
        """Print out verbose output related to web `response` from activity `name`."""
        log_section("headers:\n", response.headers, divider_name=name, verbosity=70)
        log_section("status_code:", response.status_code, verbosity=50)
        log_section("text:\n", response.text, verbosity=75)
        try:
            json_text = response.json()
            log_section("json:\n", json_text)
        except Exception:
            pass
        log.divider(func=log.verbose)

    def response_complete(self, args):
        """Wait for an aysnchronous web response, do debug logging,  check for errors."""
        response = background.background_complete(args)
        self.dump_response("Response: ", response)
        self.check_error(response)
        return response
    
    post_complete = get_complete = repost_complete = response_complete

    def get(self, relative_url):
        """HTTP(S) GET `relative_url` and return the requests response object."""
        args = self.get_start(relative_url)
        return self.get_complete(args)
    
    @background.background
    def get_start(self, relative_url):
        """Initiate a GET running in the background, do debug logging."""
        url = self.abs_url(relative_url)
        log_section("GET:", url, divider_name="GET: " + url.split("&")[0])
        return self.session.get(url)

    def post(self, relative_url, *post_dicts, **post_vars):
        """HTTP(S) POST `relative_url` and return the requests response object."""
        args = self.post_start(relative_url, *post_dicts, **post_vars)
        return self.post_complete(args)

    @background.background
    def post_start(self, relative_url, *post_dicts, **post_vars):
        """Initiate a POST running in the background, do debug logging."""
        url = self.abs_url(relative_url)
        vars = utils.combine_dicts(*post_dicts, **post_vars)
        log_section("POST:", vars, divider_name="POST: " + url)
        return self.session.post(url, data=vars)
    
    def repost(self, relative_url, *post_dicts, **post_vars):
        """First GET form from ``relative_url`,  next POST form to same
        url using composition of variables from *post_dicts and **post_vars.

        Maintain Django CSRF session token.
        """
        args = self.repost_start(relative_url, *post_dicts, **post_vars)
        return self.repost_complete(args)

    def repost_start(self, relative_url, *post_dicts, **post_vars):
        """Initiate a repost,  first getting the form synchronously and extracting
        the csrf token,  then doing a post_start() of the form and returning
        the resulting thread and queue.
        """
        response = self.get(relative_url)
        csrf_values= html.fromstring(response.text).xpath(
            '//input[@name="csrfmiddlewaretoken"]/@value'
            )
        if csrf_values:
            post_vars['csrfmiddlewaretoken'] = csrf_values[0]
        return self.post_start(relative_url, *post_dicts, **post_vars)

    """
    {'time_remaining': '3:57:58', 'user': 'jmiller_unpriv', 'created_on': '2017-02-23 16:12:55', 'type': 'instrument', 'is_expired': False, 'status': 'ok', 'name': 'miri'}
    """
    def fail_if_existing_lock(self):
        """Issue a warning if self.locked_instrument is already locked."""
        response = self.get("/lock_status/"+self.username+"/")
        log.verbose("lock_status:", response)
        json_dict = utils.Struct(response.json())
        if (json_dict.name and (not json_dict.is_expired) and (json_dict.type == "instrument") and (json_dict.user == self.username)):
            log.fatal_error("User", repr(self.username), "has already locked", repr(json_dict.name),
                            ".  Failing to avert collisions.  User --logout or logout on the website to bypass.")

    def login(self, next="/"):
        """Login to the CRDS website and proceed to relative url `next`."""
        response = self.repost(
            "/login/", 
            username = self.username,
            password = self.password, 
            instrument = self.locked_instrument,
            next = next,
            )
        self.check_login(response)
        
    def check_error(self, response):
        """Call fatal_error() if response contains an error_message <div>."""
        self._check_error(response, '//div[@id="error_message"]', "CRDS server error:")

    def check_login(self, reseponse):
        """Call fatal_error() if response contains an error_login <div>."""
        self._check_error(reseponse, '//div[@id="error_login"]',
                          "Error logging into CRDS server:")
        self._check_error(reseponse, '//div[@id="error_message"]',
                          "Error logging into CRDS server:")

    def _check_error(self, response, xpath_spec, error_prefix):
        """Extract the `xpath_spec` text from `response`,  if present call fatal_error() with
        `error_prefix` and the response `xpath_spec` text.
        """
        error_msg_parse = html.fromstring(response.text).xpath(xpath_spec)
        error_message = error_msg_parse and error_msg_parse[0].text.strip()
        if error_message:
            if error_message.startswith("ERROR: "):
                error_message = error_message[len("ERROR: "):]
            log.fatal_error(error_prefix, error_message)

    def logout(self):
        """Login to the CRDS website and proceed to relative url `next`."""
        self.get("/logout/")

    '''
    def upload_file(self, relative_url, *post_dicts, **post_vars):
        file_var = post_vars.pop("file_var", "file")
        file = post_vars.pop("file")
        content_type = post_vars.pop("content_type", "utf-8")
        fields = dict(post_vars)
        fields[file_var] = (file, open(file, "rb"), "text/plain") 
        encoder = MultipartEncoder(fields=fields)
        headers={'Content-Type': encoder.content_type}
        response = self.repost(relative_url, data=encoder, headers=headers)
        # monitor = MultipartEncoderMonitor(encoder, self.monitor_upload)
        # headers={'Content-Type': monitor.content_type}
        return response

    def monitor_upload(self, encoder, length):
        log.verbose("Upload monitor:", encoder, length)

    '''

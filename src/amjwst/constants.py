import os
import astropy.units as u
import re

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".fits"}

JWST_DATALABS_PATH = os.environ.get("JWST_DATALABS_PATH", "/media/home/data/user")
JWST_FILTERS = ['f115', 'f150', 'f277', 'f444']

# Resolution: 2 × 2k × 2k detectors (arranged 2×2) per module
JWST_OPT_RES_NIRCam_SHORT = 0.0317 # arcsec/pix
# Resolution: 2k × 2k detector per module (only one tile)
JWST_OPT_RES_NIRCam_LONG = 0.063 # arcsec/pix

JWST_MAX_HALF_RADIUS = 95 * u.arcmin
HST_MAX_HALF_RADIUS = 2.5 * u.arcmin

# --- JWST Field of View Areas in deg^2 ---

# NIRCam single module (A or B): 2.2' x 2.2'
JWST_NIRCAM_MODULE_FOV_DEG2 = 0.00134 * u.deg * u.deg 

# NIRCam both modules combined (A+B): 2.2' x 4.4'
JWST_NIRCAM_FULL_FOV_DEG2 = 0.00269 * u.deg * u.deg 

# MIRI imaging (~1.23' x 1.88')
JWST_MIRI_FOV_DEG2 = 0.00064 * u.deg * u.deg

# JWST stage3 regex based on https://jwst-pipeline.readthedocs.io/en/stable/jwst/data_products/file_naming.html
STAGE3_REGEX = re.compile(
    r'^(?!.*(?:segm|_psfstack|grism|timeseries|_ts|coron))' # reject non-imaging
    r'jw\d{5}-\w+_'                        # jw + 5 digits + dash + AC_ID + underscore
    r'(?:t\d{3}|[sbv]\d{9})'               # t + 3 digits OR s/b/v + 9 digits
    r'(?:-epoch\d)?_'                      # optional -epochX
    r'(?:nircam_clear)'                    # NIRCam clear only
    r'[\w\-]+'                             # filter/grating list
    r'(?:-[\w\-]+)?'                       # optional subarray (with preceding -)
    r'_\w+(?:-\w+)?',                      # product type + optional -ACT_ID
    re.IGNORECASE
)

# Some cutout configs
MIN_CUTOUT_SIZE = 12
CUTOUT_FACTOR = 3.5
CUTOUT_RES = 224

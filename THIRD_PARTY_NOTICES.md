# Third-party software in Memory

Memory includes or bundles the following open-source software. Their licenses permit redistribution; this file
satisfies their notice requirements. The packaged app (Memory.exe) also contains the Python runtime and the
libraries below, along with their own dependencies.

| Component | License | Where |
|---|---|---|
| [three.js](https://github.com/mrdoob/three.js) and OrbitControls, r170 | MIT, © 2010–2024 three.js authors | `frontend/vendor/` |
| [Python](https://www.python.org/) | PSF License | bundled runtime |
| [FastAPI](https://github.com/fastapi/fastapi) | MIT | bundled |
| [Starlette](https://github.com/encode/starlette) | BSD-3-Clause | bundled |
| [Uvicorn](https://github.com/encode/uvicorn) | BSD-3-Clause | bundled |
| [Pydantic](https://github.com/pydantic/pydantic) | MIT | bundled |
| [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) | MIT | bundled |
| [MSAL for Python](https://github.com/AzureAD/microsoft-authentication-library-for-python) | MIT | bundled |
| [Requests](https://github.com/psf/requests) | Apache-2.0 | bundled |
| [HTTPX](https://github.com/encode/httpx) | BSD-3-Clause | bundled |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | BSD-3-Clause | bundled |
| [python-multipart](https://github.com/Kludex/python-multipart) | Apache-2.0 | bundled |
| [certifi](https://github.com/certifi/python-certifi) | MPL-2.0 | bundled |
| [PyInstaller](https://pyinstaller.org/) bootloader | GPL-2.0 with the bootloader exception (no obligations for the bundled app) | `Memory.exe` |

## three.js license (MIT)

Copyright © 2010–2024 three.js authors

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

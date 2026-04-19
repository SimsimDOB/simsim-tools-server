# Changelog

## [0.2.0](https://github.com/SimsimDOB/simsim-tools-server/compare/v0.1.0...v0.2.0) (2026-04-19)


### Features

* add additional allowed origin for CORS middleware ([6167203](https://github.com/SimsimDOB/simsim-tools-server/commit/6167203f8eb968c215268a668ea8dc22e4ac8d73))
* add API prefix to router and update endpoint path for summonses count ([4b3573f](https://github.com/SimsimDOB/simsim-tools-server/commit/4b3573fa4a5681a300067144a8f7d9efca005656))
* add CORS middleware to FastAPI app and fix image to PIL ([d3e3487](https://github.com/SimsimDOB/simsim-tools-server/commit/d3e348709e8895a24844de100d3eeccf2aecd5d9))
* add dev dependencies and configure pytest for testing ([810b673](https://github.com/SimsimDOB/simsim-tools-server/commit/810b673148a6e555f6e6e3b8e0f9b983c9c3bedc))
* add download endpoint and fix response key in pdf_merge ([cdaaaa4](https://github.com/SimsimDOB/simsim-tools-server/commit/cdaaaa49fed2a697d655989d6eebf0fa3c8160e4))
* add download endpoint to API router ([ffbe9bd](https://github.com/SimsimDOB/simsim-tools-server/commit/ffbe9bd9f3f9f9024e414fc0190874850b0bb8ee))
* add justfile for run and deploy commands and remove old Makefile ([d331bf5](https://github.com/SimsimDOB/simsim-tools-server/commit/d331bf530656f4dc8c0b907117acddb4afbe53c6))
* add merge command to justfile for streamlined PR handling ([60d7ad1](https://github.com/SimsimDOB/simsim-tools-server/commit/60d7ad1fb7b676a416bbf1571f8828eab55eba00))
* add PDF merging functionality with support for HEIC/HEIF images ([bd7577e](https://github.com/SimsimDOB/simsim-tools-server/commit/bd7577edc5f218fc6c9eef39052ea8766a74d5d0))
* add pdf_merge endpoint and update temporary file handling ([8bd4574](https://github.com/SimsimDOB/simsim-tools-server/commit/8bd4574638eeebf7ebb1cd2867e2146dbaf7c216))
* add ping endpoint and include api_v1_router in main application ([335470f](https://github.com/SimsimDOB/simsim-tools-server/commit/335470f1f786633ea0591930918b08bcaf320c00))
* add pre-commit configuration for ruff linting and formatting ([bc19091](https://github.com/SimsimDOB/simsim-tools-server/commit/bc190910d4be831c57773f865db2cd5a02a5b4d3))
* add release-please workflow and configuration files ([226b33f](https://github.com/SimsimDOB/simsim-tools-server/commit/226b33fdb357c29b4f1b520d04ea92adb9a9fdae))
* add ruff for linting and formatting with configuration in pyproject.toml and workflow ([ca34928](https://github.com/SimsimDOB/simsim-tools-server/commit/ca34928e7ea121ce9ef6ab77165d82313972c7aa))
* add ZIP support for PDF merging functionality ([4bde8c0](https://github.com/SimsimDOB/simsim-tools-server/commit/4bde8c00f4b53d4d30e45c1b5b6113945be9162d))
* apply EXIF orientation correction to images before merging ([021d8d7](https://github.com/SimsimDOB/simsim-tools-server/commit/021d8d76e7cb895c719104b56a5041d4f5e07cbe))
* enhance PDF processing with logging and error handling ([dd30b62](https://github.com/SimsimDOB/simsim-tools-server/commit/dd30b6242c2efc45fe03e1d1fc46d9053f91f5ab))
* implement image resizing in PDF merge service ([5ec6271](https://github.com/SimsimDOB/simsim-tools-server/commit/5ec62719aa8d59ddfd3ae2eb680e37398ba67b67))
* implement logging setup for application ([fed54c6](https://github.com/SimsimDOB/simsim-tools-server/commit/fed54c659024cd7142d3e5ef2f775569d196f564))
* initialize project structure with FastAPI, Docker, and Poetry setup ([9991c90](https://github.com/SimsimDOB/simsim-tools-server/commit/9991c90ef8e8bdde3ccc0f8bf0c88b9361d90986))
* remove download endpoint and update pdf_merge response to stream merged PDFs ([4bc5c4f](https://github.com/SimsimDOB/simsim-tools-server/commit/4bc5c4f5b47d50d30d0e096699c8cc9845d12015))
* remove download endpoint from API router ([17a0364](https://github.com/SimsimDOB/simsim-tools-server/commit/17a0364b2500cacf0e5505703e34ac1fc1b3d277))
* update Dockerfile to exclude dev dependencies during installation ([ae6f1ca](https://github.com/SimsimDOB/simsim-tools-server/commit/ae6f1ca7a5dd353e7032f6eaf57c73ad5641bb54))


### Bug Fixes

* ensure branch is up to date before merging pull requests ([6ecfb7b](https://github.com/SimsimDOB/simsim-tools-server/commit/6ecfb7b11383576810e68be2af02c44191ff9bb4))
* ensure main branch is specified for push events in ruff workflow ([f07eeb1](https://github.com/SimsimDOB/simsim-tools-server/commit/f07eeb16b0b718e20935d1389f3dc43cdc1b8b2f))
* handle errors in summonses count and log PDF length ([a73f1fe](https://github.com/SimsimDOB/simsim-tools-server/commit/a73f1fea01b02c467ef6befa597c7cc070e5a208))
* restructure main function ([fd15b9f](https://github.com/SimsimDOB/simsim-tools-server/commit/fd15b9f0a03d4ec0bb7ebfe9f027f2a8d1fdbfa9))
* update API prefix to /api/v1 and correct endpoint path for summonses count ([b68701f](https://github.com/SimsimDOB/simsim-tools-server/commit/b68701f54d0ca470cd0ab18f673ae97010041cef))
* update CORS middleware to allow all origins ([0d42134](https://github.com/SimsimDOB/simsim-tools-server/commit/0d42134f42243212b256d2087850b5d83542535f))
* update response keys for removed count and removed pages in summonses count endpoint ([174b7c1](https://github.com/SimsimDOB/simsim-tools-server/commit/174b7c18326c06a4b67f38ab8866069e51ffe940))

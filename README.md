# Wiki.js DOCX Populator and LD+JSON Service

This repo contains tools to parse a `.docx` document, populate a Wiki.js
instance with its content, and serve the content as either a webpage (if
visiting with a browser) or as machine-readable LD+JSON via a microservice.

The script converts a structured Word document into a series of nested wiki
pages using the document's headings to build the hierarchy. A microservice is
layered in front of Wiki.js, using Nginx, to provide a JSON-LD representation of
the wiki pages.

## Features

- DOCX to HTML conversion: uses `mammoth` to convert a `.docx` file into HTML.
- Hierarchical Page Creation: Parses the document based on heading levels
  (Heading 1, Heading 2, etc.) to create parent and child pages in Wiki.js.
- Automatic URL Generation: Creates URLs for each page based on the heading
  text, handling path nesting for child pages.
- Table of Contents: Generates a Table of Contents, indented to indicate page
  structure.
- Footnote Support: Extracts footnotes from the original `.docx` file and
  injects them as HTML footnote definitions at the bottom of each relevant wiki
  page.
- Wiki Management: Includes an option to purge all existing pages (except the
  homepage).
- LD+JSON microservice: A Flask application that queries the Wiki.js GraphQL API
  and formats the content as JSON-LD.
- Content Negotiation: Includes an Nginx config to route requests to either
  Wiki.js or the LD+JSON microservice based on the `Accept` header.

## Components

1. `populator/`: Contains the main python scripts for parsing the document and
   populating the wiki.
   - `populate_wiki.py`: The main script. Calls a module to parse the document
     and then creates pages on Wiki.js.
   - `parse_book.py`: Handles the DOCX-to-HTML conversion and document tree
     parsing.

2. `gql_microservice/`:
   - `service.py`: A Flask microservice that fetches page data from Wiki.js and
     repackages it as LD+JSON.

3. `queries/`: Stores the GraphQL query and mutation files used to interact with
   the Wiki.js API.
   - `create_page.gql`: Mutation to create a new wiki page.
   - `delte_page.gql`: Mutation to delete a page by its ID.
   - `get_page.gql`: Query to retrieve a single page's content (based on its path).
   - `list_pages.gql`: Lists all pages.

4. `nginx-conf/`:
   - `gql-service`: An Nginx server block configuration to reverse proxy the
     Wiki.js website. It is configured to route requests to the Flask microservice
     if the `Accept` header is `application/json+ld` or `application/json`, or to
     Wiki.js otherwise.

## Setup

**Clone the Repository:**

```bash
git clone git@github.com:jgoodell2/LEBOK.git
cd LEBOK
```

**Install Dependencies:**:

```bash
pip install -r requirements.txt
```

**Create environment file:** Make a `.env` file in the project root directory
with the following variables. The populator and the microservice use this file.

```ini, toml
# URL to your Wiki.js GraphQL endpoint
API_URL=http://your-wiki-domain.com/graphql

# A Wiki.js API Key. Generate this in the Admin section of Wiki.js (your-wiki-domain.com/a/api)
API_KEY=your-api-key-goes-here

# The locale to use for all wiki operations
WIKI_LOCALE=en

# The base URL of your wiki (for generating links)
WIKI_URL=http://your-wiki-domain.com

# The absolute or relative path to the `queries` directory
QUERIES_BASEPATH=./queries
```

## Usage

1.  ### Populating the wiki

    The `populate_wiki.py` script is used to parse your `.docx` file and create
    the pages in Wiki.js.
    **Basic usage:**

    ```bash
    python populator/populate_wiki.py path/to/your/document.docx
    ```

    **Options:**
    - `--purge`: Deletes all existing pages (except the homepage) before
      populating. Useful for a clean import.

    ```bash
    python populator/populate_wiki.py --purge path/to/your/document.docx
    ```

    - `--purge-only`: Deletes all pages (except the homepage) and exits without populating.

    ```bash
    python populator/populate_wiki.py --purge-only
    ```

2.  ### Running the LD+JSON Microservice

    The Flask microservice runs as a separate program. When it receives a request
    for a wiki page, it queries the Wiki.js API and returns the page as LD+JSON
    data.

    You can run it locally for development or deploy it to production.

    #### Running Locally

    For development, you can run the Flask service directly:

    ```bash
    python gql_microservice/service.py
    ```

    The service will listen on port `9000` by default.

    #### Deploying to Production (Linux)

    There is a deployment script provided to deploy the microservice as a
    `systemd` service using `gunicorn`.

    ##### Automatic Deployment
    1. **Edit the script:** Change the `DEV_REPO_PATH` variable in the script to
       match the location where you cloned the repository, and change `PROD_PATH`
       to match the location where you will deploy the service.

    2. **Run the script:**

       ```bash
       sudo bash gql_microservice/deploy_lebok_service.sh
       ```

       The script will:
       - Create a system user name `lebok`.
       - Create the production directory at `/opt/lebok-microservice/` (or
         wherever you configure it).
       - Sync the necessary project files (microservice, queries, pip
         requirements) to the production directory.
       - Create a python virtual environment at `env/`.
       - Link `lebok-microservice.service` to `/etc/systemd/system`.
       - Reload `systemd` and restart the service.

    3. **Start on boot:** If deploying the microservice for the first time, run
       `systemctl enable
lebok-microservice` to allow it to start automatically on boot.

3.  ### Nginx Configuration

    To enable content negotiation, you can use the provided Nginx configuration
    as a reverse proxy. For this to work, Nginx needs to be installed.

    The configuration in `nginx-conf/gql-service` is set up to:
    1. Listen on port `80`.
    2. Define two `upstream` servers:
       - `web_server`: Your main Wiki.js instance (defaults to `127.0.0.1:8080`).
       - `graphql_handler`: The Flask microservice (defaults to `127.0.0.1:9000`).

    3. Use a `map` directive to check the `Accept` header. If it contains
       `application/json` or `application/ld+json`, it routes the request to
       `graphql_handler`.
    4. All other requests are proxied to `web_server`.

    **To use it:**
    1.  Update the `upstream web_server` block in `nginx-conf/gql-service` to
        point to your running Wiki.js instance.
    2.  Ensure the `upstream graphql_handler` points to where your Flask
        microservice is running.
    3.  Copy or link this configuration into your Nginx `sites-available`
        directory and enable it.
        - Enabling it usually involves creating a symbolic link to the
          configuration file in your Nginx `sites-enabled` directory.
    4.  Reload Nginx.

              Now, visiting `http://your-server:8080/en/home` in a browser will show the
              Wiki.js page, while a request like `curl -H "Accept: application/ld+json"

        http://your-server:8080/en/home` will return the JSON-LD output from the
        microservice.

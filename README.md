
<div align="center">

  <h3 align="center">Python Party Downloader (kemono/coomer)</h3>

  <p align="center">
    Just something I threw together for fun
    <br />
  </p>
</div>



<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
      <ul>
        <li><a href="#download">Download from Kemono and Coomer</a></li>
        <li><a href="#update">Update</a></li>
        <li><a href="#search">Search</a></li>
      </ul>
    <li><a href="#roadmap">Roadmap</a></li>
  </ol>
</details>



<!-- ABOUT THE PROJECT -->
## About The Project

Simply put, I got bored one night and threw this project together to pass the time.

<p align="right">(<a href="#top">back to top</a>)</p>


<!-- GETTING STARTED -->
## Getting Started

I'm not sure if something like this would be welcome on pypi, so I'm just hosting it here on github for now. Quick install instructions

### Prerequisites

Just have a modern version of python. ^3.9 should be fine. If you want support for 3.7 or 3.8 just open an issue. I just need to change some typing items and imports for those to work.

- Ubuntu 22.04
  ```sh
  apt-get install python3 python3-pip
  ```

- Arch/Manjaro (I'm more of an Arch guy)
  ```sh
  sudo pacman -S python python-pip
  ```

### Installation

You can either clone the repo or install from Releases.

#### Installation from Releases

1. Just do it, I guess. \shrugs (This is the latest link as of this post, check releases)
   ```sh
   pip install https://github.com/darkdragn/party/releases/download/v0.6.1/party-0.6.1-py3-none-any.whl
   ```

#### Installation from source

1. Clone the repo
   ```sh
   git clone https://github.com/darkdragn/party.git
   ```
2. CD into the source dir
   ```sh
   cd party
   ```
3. Install 
   ```sh
   pip install .
   ```

<p align="right">(<a href="#top">back to top</a>)</p>



<!-- USAGE EXAMPLES -->
## Usage
  Party has 4 basic commands

 > party \<command>

 ```sh
  kemono: Download from kemono
  coomer: Download from coomer
  update: Checks for and downloads new posts
  search: Find creators based on username or id
  ```
  
### Download
***Kemono and Coomer***

  A basic breakdown of the options

  ```sh
  Usage: party kemono [OPTIONS] SERVICE USER_ID
      Quick download command for kemono.party
    Arguments:
      SERVICE  Specify the service to pull from; Ex(patreon,fanbox,onlyfans)
               [required]
      USER_ID  User id from the url or name from search  [required]
    Options:
      --site TEXT                     [default: https://kemono.party]
      --files / --no-files            [default: files]
      --exclude-external / --no-exclude-external
                                      [default: exclude-external]
      -l, --limit INTEGER             Number of posts to parse. Starts from newest
                                      to oldest.
      --post-id / --no-post-id        Sets file_format to
                                      {ref.post_id}_{ref.filename}, mutually
                                      exclusive with post_title, ordered short and
                                      file_format
      -e, --exclude-extension TEXT    File extension to exclude
      -w, --workers INTEGER           Number of open download connections
                                      [default: 4]
      --name TEXT                     If you provided an id in the argument, you
                                      can provide a name here to skip user db
                                      pull/search.
      -d, --directory TEXT            Specify an output directory
      --post-title / --no-post-title  Sets file_format to
                                      {ref.post_title}_{ref.filename}, mutually
                                      exclusive with post_id, ordered_short and
                                      file_format  [default: no-post-title]
      --ordered-short / --no-ordered-short
                                      Sets file_format to {ref.post_id}_{ref.index
                                      :03}.{ref.extension}, mutually exclusive
                                      with post_id, post_title and file_format
                                      [default: no-ordered-short]
      --file-format TEXT              Used to set the output file format. Mutually
                                      exclusive with post_id, post_title and
                                      ordered short. For custom options, see
                                      post.py for schema fields. For example,
                                      {ref.post_id}_{ref.index:03}_{ref.filename}
                                      would accomplish combining post_id and
                                      ordering the files based on appearance in
                                      the post while keeping the original filename
                                      and extension  [default: {ref.filename}]
      --help                          Show this message and exit.
```

Examples

- Download something from kemono
  ```sh
  party kemono patreon diives
  ```

- Download something from coomer
  ```sh
  party coomer onlyfans belledelphine
  ```

- Download from coomer, exclude pictures, and limit to 2 downloads
  ```sh
  party coomer fansly forgottenlovechild -e jpg -e jpeg -e png -w 2
  ```

Party will check for existing files while downloading, so incomplete archives can be completed with kemono/coomer or with update. 

### Update

- Update an existing directory
  ```sh
  party update diives
  ```
  - This will skip creator list download, since we have that data.
  - If the creator was initially downloaded with extensions excluded (option -e), update will retain those exclusions.

### Search

Search supports all options kemono and coomer take, e.g. -e, -w, -d, -l

- Search for a user
  ```sh
  party search belk
  ```

- Search for a user and select results interactively
  ```sh
  party search belk -i
  +-------+------------------+--------------------+---------+
  | Index |       Name       |         ID         | Service |
  +-------+------------------+--------------------+---------+
  |   0   |  Belkos Fanbox   | 877689163103764480 | discord |
  |   1   |     belkadog     |      7025886       | patreon |
  |   2   | Belksasar3DPrint |      37766530      | patreon |
  |   3   |      Belko       |      39123643      |  fanbox |
  +-------+------------------+--------------------+---------+
   Index selection: : 3
   Downloading Belko using default options...
   Downloading from user: Belko
   0%|          | 1/909 [00:00<11:57
  ```

- A more specific search
  ```sh
  party search --site coomer --service fansly forgotten -w 3 -e jpg
  +-------+--------------------+--------------------+---------+
  | Index |        Name        |         ID         | Service |
  +-------+--------------------+--------------------+---------+
  |   0   | forgottenlovechild | 434514358358253568 |  fansly |
  +-------+--------------------+--------------------+---------+
  ```
<p align="right">(<a href="#top">back to top</a>)</p>

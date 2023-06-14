
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
      <ul>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">I nstallation</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
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
   pip install https://github.com/darkdragn/party/releases/download/v0.4.4/party-0.4.4-py3-none-any.whl
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

- Download something from kemono
  ```sh
  party kemono patreon diives
  ```

  A basic breakdown of the options
  > party kemono \<service> \<creator> [options]

        service: Ex. patreon, fantia, onlyfans
        user_id: either name or id of the user
        base_url: Swapable for coomer.party
        files: add post['file'] to downloads
        exclude_external: filter out files not hosted on *.party
        limit: limit the number of posts we pull from
        ignore_extenstions: drop files with these extenstions
        workers: number of open connections allowed
        name: skip downloading the user db, generate user with name, service, user_id

- Download something from coomer
  ```sh
  # party coomer <service> <creator> [options] // only service used to be onlyfans, but now fansly is supported
  party coomer onlyfans belledelphine

  # Second example for fansly
  party coomer fansly forgottenlovechild
  ```

- Update an existing directory
  ```sh
  # Note: This will skip creator list download, since we have that data
  party update diives
  ```

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
  party search --site coomer --service fansly forgotten
  +-------+--------------------+--------------------+---------+
  | Index |        Name        |         ID         | Service |
  +-------+--------------------+--------------------+---------+
  |   0   | forgottenlovechild | 434514358358253568 |  fansly |
  +-------+--------------------+--------------------+---------+
  ```
<p align="right">(<a href="#top">back to top</a>)</p>

# democraciv-banking-django

![Python Version](https://img.shields.io/badge/python-3.6%20%7C%203.7%20%7C%203.8%20%7C%203.9-blue) ![Django Version](https://img.shields.io/badge/Django-3-blue)

Banking Platform built with Django & PostgreSQL for a role-playing community to simulate a bank & economy. 


## Features

* Register & Login
* Create, edit & delete Bank Accounts in different currencies
* Send money between Bank Accounts via their IBANs (International Bank Account Number)
* View transaction records of your Bank Accounts
* Export & download transaction records of your Bank Accounts in `.json`, `.csv` or `.xlsx`
* Create, edit & delete Organizations
* Invite & remove other users as employees to Organizations
* Accept & refuse invitations from Organizations
* Transfer ownership of Organization to other employee
* Leave Organizations
* Create, edit & delete shared bank accounts for Organizations
* View all Organizations that decided to be listed on the Marketplace 
* Link Discord Account via OAuth2
* Receive Notifications via Discord DM whenever 1) someone sends you money, 2) someone invites you to their Organization, 3) you're fired from an Organization
* Password Reset via Discord DM

--- 

* Admin Dashboard 
* Per-Object permissions realized with django-guardian
* Private API for a Discord Bot built with django-rest-framework



## Requirements

* Python >=3.6 *(only tested on 3.7 & 3.8)*
* Django >=3.0 
* PostgreSQL >=9.6 

Run `pip install -U -r requirements.txt` in your virtualenv to install all other required dependencies.


## See in Action

Served in production via Gunicorn behind nginx. Hosted on a Hetzner Cloud VPS. HTTPs thanks to Let's Encrypt.

https://democracivbank.com

#!/usr/bin/env python3

import datetime 
import time
from brainzutils import cache
from intuitlib.enums import Scopes
from intuitlib.client import AuthClient
from quickbooks import QuickBooks
from quickbooks.objects.customer import Customer
from quickbooks.objects.invoice import Invoice, DeliveryInfo
from quickbooks.objects.detailline import SalesItemLineDetail
from quickbooks import exceptions
from intuitlib.exceptions import AuthClientError

import config

from icecream import ic


class QuickBooksInvoiceSender():

    def __init__(self):
        QuickBooks.enable_global()
        self.auth_client = AuthClient(
            client_id=config.QUICKBOOKS_CLIENT_ID,
            client_secret=config.QUICKBOOKS_CLIENT_SECRET,
            environment=config.QUICKBOOKS_SANDBOX,
            redirect_uri=config.QUICKBOOKS_REDIRECT_URI
        )
        cache.init(host=config.REDIS_HOST, port=config.REDIS_PORT, namespace=config.REDIS_NAMESPACE)


    def get_client(self):
        refresh_token = cache.get("qb_refresh_token")
        realm = cache.get("qb_realm")

        if not refresh_token or not realm:
            print("Could not fetch OAuth credentials from redis.")
            print("Load https://test.metabrainz.org/admin/quickbooks/ to push the credentials to redis.")
            return None

        return QuickBooks(
            auth_client=self.auth_client,
            refresh_token=refresh_token,
            company_id=realm
        )

    def mark_invoice_sent(self, client, invoice):
        invoice.EmailStatus = "EmailSent"
        if invoice.DeliveryInfo is None:
            invoice.DeliveryInfo = DeliveryInfo()
            invoice.DeliveryInfo.DeliveryType = "Email"
            
        invoice.DeliveryInfo.DeliveryTime = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%dT%H:%M:%S")
        try:
            invoice.save(qb=client)
            return True
        except exceptions.ValidationException as err:
            print(err.detail)
            return False

    def send_invoices(self):

        client = self.get_client()
        if not client:
            return

        invoices = Invoice.query("select * from invoice order by metadata.createtime desc maxresults 300", qb=client)
        if not invoices:
            print("Cannot fetch list of invoices")
            return

        for invoice in invoices:
            if invoice.EmailStatus == "EmailSent":
                continue

            print("Invoice %s with status %s" % (invoice.DocNumber, invoice.EmailStatus))
            if float(invoice.TotalAmt) == 0.0:
                print("  marking zero amount invoice %s as sent." % invoice.DocNumber)
                self.mark_invoice_sent(self, client, invoice)
                continue

            customer = Customer.get(int(invoice.CustomerRef.value), qb=client)
            if customer.Notes.find("donotsend") >= 0:
                print("  marking donotsend invoice %s as sent, without sending." % invoice.DocNumber)
                self.mark_invoice_sent(client, invoice)

            if invoice.EmailStatus == "NotSet":
                print("  To '%s' marked as NotSet." % customer.DisplayName)
                while True:
                    print("  Send [s], Mark sent [m], Ignore [i]:", end="")
                    resp = input().strip().lower()
                    if resp is None or len(resp) == 0 or resp[0] not in "smi":
                        print("  select one of the given options!")  

                    if resp[0] == "s":
                        self.send_invoice(client, invoice)
                        print("  invoice sent!")
                        break
                    elif resp[0] == "m":
                        self.mark_invoice_sent(client, invoice)
                        print("  invoice marked as sent, without being sent!")
                        break
                    else:
                        break
            


qb = QuickBooksInvoiceSender()
qb.send_invoices()

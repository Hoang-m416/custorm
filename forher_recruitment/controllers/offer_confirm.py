from odoo import http, _
from odoo.http import request


class OfferController(http.Controller):

    @http.route(['/offer/confirm/<int:offer_id>/<string:token>'], type='http', auth="public", website=True)
    def confirm_offer(self, offer_id, token, **kwargs):
        decision = kwargs.get('decision')
        offer = request.env['forher.offer.letter'].sudo().browse(offer_id)
        if not offer or not offer.exists():
            return request.render("forher_recruitment.offer_invalid", {})

        success = offer.applicant_confirm(token, decision)
        if not success:
            return request.render("forher_recruitment.offer_invalid", {})

        if decision == 'accept':
            return request.render("forher_recruitment.offer_confirmed", {'offer': offer})
        else:
            return request.render("forher_recruitment.offer_rejected", {'offer': offer})

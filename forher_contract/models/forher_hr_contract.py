from odoo import fields, models, api, _
from datetime import datetime, timedelta
import calendar
import logging

_logger = logging.getLogger(__name__)


class ForHerHrContract(models.Model):
    _name = 'forher.hr.contract'
    _description = 'ForHer HR Contract'
    _inherit = ['hr.contract']

    name = fields.Char(string='Contract Reference', required=False, copy=False, readonly=True)
    state = fields.Selection([
        ('draft', 'New'),
        ('waiting_approval', 'Waiting for Approval'),
        ('open', 'Running'),
        ('close', 'Expired'),
        ('cancel', 'Cancelled')
    ], string='Status', group_expand=True, copy=False,
        tracking=True, help='Status of the contract', default='draft')


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('forher.hr.contract') or _('New')
        return super(ForHerHrContract, self).create(vals_list)


    def action_submit_for_approval(self):
        for record in self:
            if record.state != 'draft':
                continue
            record.state = 'waiting_approval'
            record.message_post(body="Contract submitted for approval.")

            # Send email to board members
            record._send_approval_notification()

    def _send_approval_notification(self):
        template = self.env.ref('forher_contract.forher_contract_approval_request_template', raise_if_not_found=False)
        if not template:
            return

        company = self.employee_id.company_id if self.employee_id else self.env.company

        board_group = self.env.ref('forher_company_overview.forher_group_board', raise_if_not_found=False)
        if not board_group:
            return

        board_users = self.env['res.users'].search([
            ('groups_id', 'in', board_group.id),
            ('company_ids', 'in', company.id),
            ('active', '=', True)
        ])

        board_employees = self.env['hr.employee'].search([
            ('user_id', 'in', board_users.ids),
            ('active', '=', True)
        ])

        # Collect work emails
        work_emails = []
        for employee in board_employees:
            if employee.work_email:
                work_emails.append(employee.work_email)

        # Fallback to user emails if no work_email found
        if not work_emails:
            user_emails = [user.email for user in board_users if user.email]
            work_emails = user_emails

        if work_emails:
            # Send email using the template with email_to
            email_to = ','.join(work_emails)
            template.with_context(email_to=email_to).send_mail(self.id, force_send=True)

    @api.model
    def _cron_check_expiring_contracts(self):
        """Cron method to check for contracts expiring in the current month and send notifications to managers"""
        _logger.info("Starting monthly contract expiry check...")

        # Get current date
        today = datetime.now().date()

        # Calculate first and last day of current month
        first_day_of_month = today.replace(day=1)
        last_day_of_month = today.replace(day=calendar.monthrange(today.year, today.month)[1])

        # Find contracts expiring in the current month
        expiring_contracts = self.search([
            ('date_end', '!=', False),
            ('date_end', '>=', first_day_of_month),
            ('date_end', '<=', last_day_of_month),
            ('state', 'in', ['open'])
        ])

        _logger.info(f"Found {len(expiring_contracts)} contracts expiring in {today.strftime('%B %Y')}")

        if not expiring_contracts:
            _logger.info("No contracts expiring this month")
            return

        # Send notifications for each expiring contract
        for contract in expiring_contracts:
            contract._send_expiry_notification()
            _logger.info(f"Sent expiry notification for contract: {contract.name} (Employee: {contract.employee_id.name})")

        _logger.info("Monthly contract expiry check completed")

    def _send_expiry_notification(self):
        """Send email notification to branch managers when contract is expiring soon"""
        # Find the mail template
        template = self.env.ref('forher_contract.forher_contract_expiry_notification_template', raise_if_not_found=False)
        if not template:
            return

        # Get company of the contract
        company = self.employee_id.company_id if self.employee_id else self.env.company

        # Find branch manager group
        branch_manager_group = self.env.ref('forher_company_overview.forher_group_branch_manager', raise_if_not_found=False)
        if not branch_manager_group:
            return

        # Find all users with branch manager permissions in the same company
        branch_manager_users = self.env['res.users'].search([
            ('groups_id', 'in', branch_manager_group.id),
            ('company_ids', 'in', company.id),
            ('active', '=', True)
        ])

        if not branch_manager_users:
            return

        # Get work emails of branch managers
        branch_manager_employees = self.env['hr.employee'].search([
            ('user_id', 'in', branch_manager_users.ids),
            ('active', '=', True)
        ])

        work_emails = []
        for employee in branch_manager_employees:
            if employee.work_email:
                work_emails.append(employee.work_email)

        # Fallback to user emails if no work_email found
        if not work_emails:
            user_emails = [user.email for user in branch_manager_users if user.email]
            work_emails = user_emails

        if work_emails:
            # Calculate days until expiry
            days_until_expiry = (self.date_end - datetime.now().date()).days if self.date_end else 0

            # Send email using the template
            email_to = ','.join(work_emails)
            template.with_context(
                email_to=email_to,
                days_until_expiry=days_until_expiry
            ).send_mail(self.id, force_send=True)

    def _cron_auto_expire_contracts(self):
        """Cron method to automatically expire contracts that have passed their end date"""
        today = datetime.now().date()
        contracts_to_expire = self.search([
            ('date_end', '<', today),
            ('state', 'in', ['open', 'waiting_approval'])
        ])

        for contract in contracts_to_expire:
            contract.state = 'close'
            contract.message_post(body="Contract automatically expired due to end date passed.")

            # Update employee record if linked
            if contract.employee_id:
                vals = contract._get_employee_vals_to_update()
                if vals:
                    contract.employee_id.write(vals)

    def _get_employee_vals_to_update(self):
        if self._name == "forher.hr.contract":
            vals = {'forher_contract_id': self.id}
        else:
            vals = {'contract_id': self.id}

        if self.job_id and self.job_id != self.employee_id.job_id:
            vals['job_id'] = self.job_id.id
        if self.department_id:
            vals['department_id'] = self.department_id.id
        return vals

    def action_running_contract(self):
        for record in self:
            if record.state != 'waiting_approval':
                continue
            record.state = 'open'
            record.message_post(body="Contract approved and set to running.")

    def action_reject_contract(self):
        for record in self:
            if record.state != 'waiting_approval':
                continue
            record.state = 'cancel'
            record.message_post(body="Contract rejected and cancelled.")

    
    employee_id = fields.Many2one('hr.employee', string='Employee')
    job_id = fields.Many2one('hr.job', string='Job')
    company_id = fields.Many2one('res.company', string='Company')
    
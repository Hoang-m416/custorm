from odoo import fields, models, tools, api


class ForHerHrContractReport(models.Model):
    _name = 'forher.hr.contract.report'
    _description = 'Contract Analysis Report'
    _auto = False
    _rec_name = 'employee_id'

    # Basic Information
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    employee_name = fields.Char(string='Employee Name', readonly=True)
    employee_code = fields.Char(string='Employee Code', readonly=True)
    contract_name = fields.Char(string='Contract Name', readonly=True)

    # Contract Details
    state = fields.Selection([
        ('draft', 'Draft'),
        ('waiting_approval', 'Waiting for Approval'),
        ('open', 'Running'),
        ('close', 'Expired'),
        ('cancel', 'Cancelled')
    ], string='Status', readonly=True)

    # Organization
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    job_id = fields.Many2one('hr.job', string='Job Position', readonly=True)

    # Dates
    date_start = fields.Date(string='Start Date', readonly=True)
    date_end = fields.Date(string='End Date', readonly=True)
    contract_duration = fields.Integer(string='Contract Duration (Days)', readonly=True)
    days_to_expiry = fields.Integer(string='Days to Expiry', readonly=True)

    # Financial
    wage = fields.Monetary(string='Wage', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    wage_range = fields.Selection([
        ('0-10', 'Under 10M'),
        ('10-20', '10M - 20M'),
        ('20-30', '20M - 30M'),
        ('30-50', '30M - 50M'),
        ('50+', 'Above 50M')
    ], string='Wage Range', readonly=True)

    # Time Analysis
    year = fields.Char(string='Year', readonly=True)
    month = fields.Char(string='Month', readonly=True)
    quarter = fields.Char(string='Quarter', readonly=True)
    week = fields.Char(string='Week', readonly=True)

    # Contract Type Analysis
    contract_type = fields.Selection([
        ('temporary', 'Temporary'),
        ('permanent', 'Permanent'),
        ('probation', 'Probation')
    ], string='Contract Type', readonly=True)

    # Metrics
    total_contracts = fields.Integer(string='Total Contracts', readonly=True)
    active_contracts = fields.Integer(string='Active Contracts', readonly=True)
    expired_contracts = fields.Integer(string='Expired Contracts', readonly=True)
    pending_contracts = fields.Integer(string='Pending Approval', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    row_number() OVER () AS id,
                    c.employee_id,
                    e.name AS employee_name,
                    e.employee_code AS employee_code,
                    c.name AS contract_name,
                    c.state,
                    c.company_id,
                    c.department_id,
                    c.job_id,
                    c.date_start,
                    c.date_end,
                    c.wage,

                    -- Contract Duration
                    CASE
                        WHEN c.date_end IS NOT NULL
                        THEN (c.date_end - c.date_start)
                        ELSE NULL
                    END AS contract_duration,

                    -- Days to Expiry
                    CASE
                        WHEN c.date_end IS NOT NULL AND c.state = 'open'
                        THEN (c.date_end - CURRENT_DATE)
                        ELSE NULL
                    END AS days_to_expiry,

                    -- Wage Range
                    CASE
                        WHEN c.wage < 10000000 THEN '0-10'
                        WHEN c.wage >= 10000000 AND c.wage < 20000000 THEN '10-20'
                        WHEN c.wage >= 20000000 AND c.wage < 30000000 THEN '20-30'
                        WHEN c.wage >= 30000000 AND c.wage < 50000000 THEN '30-50'
                        WHEN c.wage >= 50000000 THEN '50+'
                        ELSE '0-10'
                    END AS wage_range,

                    -- Time Analysis
                    EXTRACT(year FROM c.date_start)::text AS year,
                    TO_CHAR(c.date_start, 'YYYY-MM') AS month,
                    CONCAT('Q', EXTRACT(quarter FROM c.date_start), '-', EXTRACT(year FROM c.date_start)) AS quarter,
                    CONCAT('W', EXTRACT(week FROM c.date_start), '-', EXTRACT(year FROM c.date_start)) AS week,

                    -- Contract Type (based on duration)
                    CASE
                        WHEN c.date_end IS NULL THEN 'permanent'
                        WHEN (c.date_end - c.date_start) <= 90 THEN 'probation'
                        ELSE 'temporary'
                    END AS contract_type,

                    -- Metrics
                    1 AS total_contracts,
                    CASE WHEN c.state = 'open' THEN 1 ELSE 0 END AS active_contracts,
                    CASE WHEN c.state = 'close' THEN 1 ELSE 0 END AS expired_contracts,
                    CASE WHEN c.state = 'waiting_approval' THEN 1 ELSE 0 END AS pending_contracts

                FROM forher_hr_contract c
                LEFT JOIN hr_employee e ON c.employee_id = e.id
                WHERE c.active = true
            )
        """ % self._table)

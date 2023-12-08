from odoo import fields, models, api, _
from odoo.addons import decimal_precision as dp
from odoo.exceptions import ValidationError
import json, requests


class JobCardBilling(models.Model):
    _name = 'job.card.billing'
    _description = 'Job Card Billing'
    _order = "id desc"

    name = fields.Char(default='New', required=True)
    job_card_id = fields.Many2one('ulccs.billing.job.card', string="Job Card")
    gate_pass_no = fields.Char(string="Gate Pass No")
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed')], string='Status', default="draft")
    materials_ids = fields.One2many('ulccs.workshop.materials', 'job_card_billing_id', string='Materials Used')
    labour_cost_ids = fields.One2many('ulccs.workshop.labour.cost', 'billing_id', string='Labour Cost')
    total_material_cost = fields.Monetary(string='Total Material Cost', compute='_compute_total_amount',
                                          digits=dp.get_precision('Product Price'), store=True)
    total_labour_cost = fields.Monetary(string='Total Labour Cost', compute='_compute_total_amount',
                                        digits=dp.get_precision('Product Price'), store=True)
    grand_total = fields.Monetary(string='Grand Total', compute='_compute_total_amount',
                                  digits=dp.get_precision('Product Price'), store=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True,
                                  default=lambda self: self.env.user.company_id.currency_id)
    hide_edit = fields.Html(string='Hide Edit', sanitize=False, compute='_compute_css', store=False)

    @api.depends('state')
    def _compute_css(self):
        for rec in self:
            if rec.state != 'draft':
                rec.hide_edit = '<style>.o_form_button_edit {display: none;}</style>'
            else:
                rec.hide_edit = False

    @api.depends('materials_ids', 'materials_ids.price_total', 'labour_cost_ids', 'labour_cost_ids.total_amount')
    def _compute_total_amount(self):
        for rec in self:
            material_cost = 0.00
            labour_cost = 0.00
            final_total = 0.00
            for line in rec.materials_ids:
                material_cost += line.price_total
            rec.total_material_cost = material_cost
            for line in rec.labour_cost_ids:
                labour_cost += line.total_amount
            rec.total_labour_cost = labour_cost
            final_total = rec.total_material_cost + rec.total_labour_cost
            rec.grand_total = final_total

    @api.onchange('job_card_id')
    def change_job_card_id(self):
        for rec in self:
            material_list = []
            materials_line_pool = self.env['ulccs.workshop.materials']
            quantity = 0.00
            rec.materials_ids = False
            rec.gate_pass_no = rec.job_card_id.gate_pass_no
            for line in rec.job_card_id.job_card_line_ids:
                if line.returned_quantity != line.quantity:
                    quantity = line.quantity - line.returned_quantity
                    material_line = material_list.append((0, 0, {
                        'product_id': line.product_id.id or False,
                        'alias_name': line.alias_name or '',
                        'part_number': line.part_number or '',
                        'lot_id': line.lot_id.id or False,
                        'quantity': quantity,
                        'product_uom': line.product_uom.id or False,
                        'unit_price': line.unit_price or 0.00,
                        'issued_date': line.issued_date or False,
                        'currency_id': self.env.user.company_id.currency_id.id
                    }))
            #                     material_list.append(material_line.id)
            rec.materials_ids = material_list

    @api.multi
    def action_confirm(self):
        """ button action confirm"""
        for rec in self:
            if rec.job_card_id.state != 'closed':
                raise ValidationError(_('Sorry, you can only choose a Job Card which is in Closed stage.!'))
            rec.name = self.env['ir.sequence'].next_by_code('job.card.billing.sequence')
            rec.state = 'confirmed'
            rec.job_card_id.state = 'billed'


class UlccsWorkshopMaterials(models.Model):
    _name = 'ulccs.workshop.materials'
    _description = 'Workshop Job Card Materials'

    job_card_billing_id = fields.Many2one('job.card.billing', string="Job Card Billing")
    product_id = fields.Many2one('product.product', string="Materials", ondelete='restrict')
    alias_name = fields.Char(string="Alias Name", related='product_id.alias_name')
    part_number = fields.Char(string="Part Number", related='product_id.default_code')
    lot_id = fields.Many2one('stock.production.lot', string="Barcode")
    quantity = fields.Float(string="Quantity")
    product_uom = fields.Many2one('uom.uom', string='Unit of Measure', ondelete='restrict')
    unit_price = fields.Monetary(string="Unit Price")
    issued_date = fields.Datetime(string="Issued On")
    price_total = fields.Monetary(string='Total', compute='_compute_total', digits=dp.get_precision('Product Price'),
                                  store=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True,
                                  default=lambda self: self.env.user.company_id.currency_id)

    @api.depends('unit_price', 'quantity')
    def _compute_total(self):
        for rec in self:
            rec.price_total = rec.unit_price * rec.quantity


class UlccsWorkshopLabourCost(models.Model):
    _name = 'ulccs.workshop.labour.cost'
    _description = 'Labour Cost'

    @api.model
    def default_get(self, fields):
        res = super(UlccsWorkshopLabourCost, self).default_get(fields)
        salary_type = ''
        hour_rate = salary = 0.00
        if not self._context.get('create_dlr_from_cron', False):
            if self._context.get('active_model') == 'dialy.labour.activity' and self._context.get('active_id'):
                activity_id = self.env['dialy.labour.activity'].browse(self._context.get('active_id'))
                if activity_id and activity_id.employee_id:
                    salary_type = activity_id.employee_id.salary_type or ''
                    salary = activity_id.employee_id.salary or 0.00
                    if salary_type == 'daily' and salary > 0.00:
                        hour_rate = salary / 8
                    elif salary_type == 'monthly' and salary > 0.00:
                        hour_rate = salary / (30 * 8)
                    else:
                        hour_rate = 0.00
                    res.update({
                        'hourly_rate': hour_rate or 0.00,
                    })
                res.update({
                    'category_id': self._context.get('maintain_head', False) or False,
                    'curr_warehouse_id': self.env.user and self.env.user.current_warehouse_id \
                                         and self.env.user.current_warehouse_id.id or False
                })
            if self._context.get('active_model') == 'all.dialy.labour.activity':
                res.update({
                    'category_id': self._context.get('maintain_head', False) or False
                })
        return res

    @api.multi
    def name_get(self):
        result = []
        for record in self:
            name = (record.employee_id and record.employee_id.name or '') + '[' + (record.job_card_id and \
                                                                                   record.job_card_id.name or '') + ']'
            result.append((record.id, name))
        return result

    employee_id = fields.Many2one('hr.employee', string="Employee")
    hourly_rate = fields.Monetary(string="Hourly Rate")
    total_hours = fields.Float(string="Total Hour(s)")
    total_amount = fields.Monetary(string="Total Amount", compute='_compute_amount_total', store=True,
                                   digits=dp.get_precision('Product Price'))
    billing_id = fields.Many2one('job.card.billing', string="Job Card Billing")
    currency_id = fields.Many2one('res.currency', string='Currency', required=True,
                                  default=lambda self: self.env.user.company_id.currency_id)
    job_card_id = fields.Many2one('ulccs.billing.job.card', string="Job Card ")
    category_id = fields.Many2one('category.configuration', string="Maintenance Head", ondelete='restrict')
    date = fields.Date(string="Date")
    work_description = fields.Char(string="Work Description")
    allowance = fields.Float(string="Allowance Amount")
    work_category_id = fields.Many2one('workshop.work.category.configuration', string="Work Category",
                                       ondelete='restrict')
    dialy_labour_id = fields.Many2one('dialy.labour.activity', string='Daily Labour Activities')
    state = fields.Selection([('draft', 'Draft'), ('in_progress', 'WIP'), ('completed', 'Completed'),
                              ('reopen', 'Reopened'), ('closed', 'Closed'), ('billed', 'Billed'),
                              ('cancelled', 'Cancelled')], string='Status', compute='get_parent_status', store=True)
    allowance_id = fields.Many2one('hr.allowance', string="Allowance")
    halting_id = fields.Many2one('halting.code', string='Halting')
    curr_warehouse_id = fields.Many2one('stock.warehouse', string='Workshop')

    @api.onchange('allowance_id')
    def onchange_allowance_id(self):
        for rec in self:
            rec.allowance = rec.allowance_id and rec.allowance_id.default_amount or 0.0

    @api.onchange('job_card_id')
    def change_job_card_id(self):
        for rec in self:
            if rec.job_card_id:
                rec.work_category_id = False
                rec.category_id = rec.job_card_id and rec.job_card_id.maintain_head_id and rec.job_card_id.maintain_head_id.id or False
                rec.curr_warehouse_id = rec.job_card_id and rec.job_card_id.unit_price and rec.job_card_id.workshop_id.id or False

    @api.onchange('category_id')
    def change_category_id(self):
        for rec in self:
            if rec.category_id:
                jobcard = self.env['ulccs.billing.job.card'].search(
                    [('maintain_head_id', '=', rec.category_id.id), ('state', 'in', ['in_progress', 'reopen']),
                     ('job_card_type', '=', 'internal'), ('workshop_id', '=', rec.curr_warehouse_id.id)])
                jobcard_list = jobcard and jobcard.ids or []
                if rec.job_card_id and rec.job_card_id.id not in jobcard_list:
                    rec.job_card_id = False
                return {'domain': {'job_card_id': [('id', 'in', jobcard_list)]}}
            else:
                rec.job_card_id = False
                all_jobcard = self.env['ulccs.billing.job.card'].search(
                    [('state', 'in', ['in_progress', 'reopen']), ('job_card_type', '=', 'internal'),
                     ('workshop_id', '=', rec.curr_warehouse_id.id)])
                all_jobcard_list = all_jobcard and all_jobcard.ids or []
                return {'domain': {'job_card_id': [('id', 'in', all_jobcard_list)]}}

    @api.multi
    @api.depends('job_card_id', 'job_card_id.state')
    def get_parent_status(self):
        for rec in self:
            rec.state = rec.job_card_id and rec.job_card_id.state or ''

    @api.depends('hourly_rate', 'total_hours', 'allowance')
    def _compute_amount_total(self):
        for rec in self:
            rec.total_amount = (rec.hourly_rate * rec.total_hours) + rec.allowance

    @api.model
    def create(self, vals):
        if self._context.get('active_model', False) and self._context.get('active_id', False):
            active_obj = self.env[self._context.get('active_model', False)].browse(
                self._context.get('active_id', False))
            if active_obj and self._context.get('active_model', False) == 'dialy.labour.activity':
                vals.update({
                    'employee_id': active_obj.employee_id and active_obj.employee_id.id or False,
                    'date': active_obj.date or False,
                    'hourly_rate': vals.get('hourly_rate', 0.0),
                })
        if self._context.get('active_model', False) in ('ulccs.billing.job.card', 'ulccs.workshop.labour.cost') and (
                vals.get('employee_id', False) or vals.get('date', False)):
            domain_list = []
            daily_domain_list = []
            if vals.get('employee_id', False):
                domain_list.append(('employee_id', '=', vals.get('employee_id', False)))
            if vals.get('date', False):
                domain_list.append(('date', '=', vals.get('date', False)))
                daily_domain_list.append(('date', '=', vals.get('date', False)))

            check_dialy_employee_records = self.env['dialy.labour.activity'].search(domain_list)
            jobcard_obj = False
            if vals.get('job_card_id'):
                jobcard_obj = self.env['ulccs.billing.job.card'].browse(vals.get('job_card_id'))

            if check_dialy_employee_records:
                for dialy_employee_record in check_dialy_employee_records:
                    if dialy_employee_record.all_activity_id and dialy_employee_record.all_activity_id.state == 'submitted':
                        raise ValidationError(
                            _('Can not update on this date! Related DLR entries are already submitted!'))
                    vals.update({
                        'dialy_labour_id': dialy_employee_record.id,
                        'category_id': jobcard_obj and jobcard_obj.maintain_head_id and jobcard_obj.maintain_head_id.id or False
                    })
            else:
                check_dialy_records = self.env['all.dialy.labour.activity'].search(daily_domain_list)
                for dialy_record in check_dialy_records:
                    if dialy_record.state == 'submitted':
                        raise ValidationError(
                            _('Can not update on this date! Related DLR entries are already submitted!'))

                    employee_obj = self.env['hr.employee'].browse(vals.get('employee_id'))

                    hour_rate = 0.00
                    if employee_obj:
                        salary_type = employee_obj.salary_type or ''
                        salary = employee_obj.salary or 0.00
                        if salary_type == 'daily' and salary > 0.00:
                            hour_rate = salary / 8
                        elif salary_type == 'monthly' and salary > 0.00:
                            hour_rate = salary / (30 * 8)
                        else:
                            hour_rate = 0.00

                    daily_labour_activity_record = self.env['dialy.labour.activity'].create({
                        'date': vals.get('date', False),
                        'employee_id': vals.get('employee_id', False),
                        'all_activity_id': dialy_record.id,
                        'available': 'yes',
                        'hourly_rate': hour_rate,
                        'manual_update': False

                    })
                    vals.update({
                        'dialy_labour_id': daily_labour_activity_record.id,
                        'category_id': jobcard_obj and jobcard_obj.maintain_head_id and jobcard_obj.maintain_head_id.id or False
                    })

        res = super(UlccsWorkshopLabourCost, self).create(vals)
        return res

    @api.multi
    def write(self, vals):
        if self._context.get('active_model', False) and self._context.get('active_id', False):
            active_obj = self.env[self._context.get('active_model', False)].browse(
                self._context.get('active_id', False))
            if active_obj and self._context.get('active_model', False) == 'dialy.labour.activity':
                if vals and self.job_card_id and self.job_card_id.state not in ['in_progress', 'reopen']:
                    raise ValidationError(_('Warning!. Could not edit!. Jobcard not in Open/In progress status!'))

                vals.update({
                    'employee_id': (active_obj.employee_id and active_obj.employee_id.id) or (
                                self.employee_id and self.employee_id.id) or False,
                    'date': active_obj.date or self.date or False,
                    'hourly_rate': vals.get('hourly_rate') or self.hourly_rate or 0.0,
                })

        if self._context.get('active_model', False) in ('ulccs.billing.job.card', 'ulccs.workshop.labour.cost') and (
                vals.get('employee_id', False) or vals.get('date', False)):
            domain_list = []
            daily_domain_list = []
            if vals.get('employee_id', False) and vals.get('date', False):
                domain_list.append(('employee_id', '=', vals.get('employee_id', False)))
                domain_list.append(('date', '=', vals.get('date', False)))
                daily_domain_list.append(('date', '=', vals.get('date', False)))
            elif vals.get('date', False) and not vals.get('employee_id', False):
                domain_list.append(('date', '=', vals.get('date', False)))
                daily_domain_list.append(('date', '=', vals.get('date', False)))
                domain_list.append(('employee_id', '=', self.employee_id.id))
            elif not vals.get('date', False) and vals.get('employee_id', False):
                domain_list.append(('date', '=', self.date))
                daily_domain_list.append(('date', '=', self.date))
                domain_list.append(('employee_id', '=', vals.get('employee_id', False)))
            check_dialy_employee_records = self.env['dialy.labour.activity'].search(domain_list, limit=1)
            if check_dialy_employee_records:
                for dialy_employee_record in check_dialy_employee_records:
                    if dialy_employee_record.all_activity_id and dialy_employee_record.all_activity_id.state == 'submitted':
                        raise ValidationError(
                            _('Can not update on this date! Related DLR entries are already submitted!'))
                    vals.update({
                        'dialy_labour_id': dialy_employee_record.id,
                    })

            else:
                check_dialy_records = self.env['all.dialy.labour.activity'].search(daily_domain_list)
                for dialy_record in check_dialy_records:
                    if dialy_record.state == 'submitted':
                        raise ValidationError(
                            _('Can not update on this date! Related DLR entries are already submitted!'))

                    if vals.get('employee_id', False):
                        employee_obj = self.env['hr.employee'].browse(vals.get('employee_id'))
                    else:
                        employee_obj = self.employee_id

                    hour_rate = 0.00
                    if employee_obj:
                        salary_type = employee_obj.salary_type or ''
                        salary = employee_obj.salary or 0.00
                        if salary_type == 'daily' and salary > 0.00:
                            hour_rate = salary / 8
                        elif salary_type == 'monthly' and salary > 0.00:
                            hour_rate = salary / (30 * 8)
                        else:
                            hour_rate = 0.00

                    daily_labour_activity_record = self.env['dialy.labour.activity'].create({
                        'date': vals.get('date', False) or self.date or False,
                        'employee_id': vals.get('employee_id', False) or (
                                    self.employee_id and self.employee_id.id) or False,
                        'all_activity_id': dialy_record.id,
                        'available': 'yes',
                        'hourly_rate': hour_rate,
                        'manual_update': False

                    })
                    vals.update({
                        'dialy_labour_id': daily_labour_activity_record.id,
                    })
        res = super(UlccsWorkshopLabourCost, self).write(vals)
        return res

    @api.constrains('total_hours')
    def _check_total_hours(self):
        if not self._context.get('create_dlr_from_cron', False) and self._context.get('active_model') not in [
            'dialy.labour.activity', 'all.dialy.labour.activity']:
            for record in self:
                if record.total_hours <= 0.0:
                    raise ValidationError(_('Warning ! Please Enter a valid working hour(s).!'))

    @api.constrains('hourly_rate')
    def _check_hourly_rate(self):
        if not self._context.get('create_dlr_from_cron', False) and self._context.get('active_model') not in [
            'dialy.labour.activity', 'all.dialy.labour.activity']:
            for record in self:
                if record.hourly_rate <= 0.0:
                    raise ValidationError(_('Warning ! Please Enter a valid Hourly Rate.!'))

    @api.multi
    def delete_labour_line(self):
        context = self._context.copy()
        if self._context.get('active_model', False) == 'dialy.labour.activity':
            parent_record_id = self and self[0] and self[0].dialy_labour_id and self[0].dialy_labour_id.id or False
            for rec in self:
                category_id = self.search([('category_id', '=', self.dialy_labour_id.multi_work_account_id.id),
                                           ('dialy_labour_id', '=', parent_record_id)])
                if len(category_id) == 1:
                    if self.dialy_labour_id.multi_work_account_id.id == rec.category_id.id:
                        raise ValidationError("Please update multi work account before Removing Activity Line")

                if rec.dialy_labour_id and rec.dialy_labour_id.state != 'not_prepared':
                    raise ValidationError("Related DLR already submitted. Please check now")
                rec.sudo().unlink()

            return {
                'view_mode': 'form',
                'view_id': self.env.ref('ulccs_workshop.dialy_labour_activity_popup_form_view').id,
                'view_type': 'form',
                'res_model': 'dialy.labour.activity',
                'res_id': parent_record_id,
                'type': 'ir.actions.act_window',
                'target': 'new',
                'context': context
            }

        else:
            for rec in self:
                if rec.dialy_labour_id and rec.dialy_labour_id.state != 'not_prepared':
                    raise ValidationError("Related DLR already submitted. Please check now")
                rec.sudo().unlink()

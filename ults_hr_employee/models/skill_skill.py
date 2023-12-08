from odoo import models, fields,api


class SkillSkill(models.Model):
    _name = 'skill.skill'
    _description = 'Skill sets'

    name = fields.Char("skill")
    # skill_code = fields.Integer("code")
    # sequence_number = fields.Char('Product Sequence Number')
    sequence_number = fields.Char("Referece",readonly=True,copy=False,default="NEW")
    _rec_name = 'sequence_number'


    @api.model
    def create(self, vals):
        sequence_number = self.env['ir.sequence'].next_by_code('skill.sequence.code')
        print(sequence_number,'=========================sequence_number')
        vals['sequence_number'] = sequence_number
        return super(SkillSkill, self).create(vals)

    def print(self):
        print(self.sequence_number,self.name)

    def name_get(self):
        res=[]
        for rec in self :
            res.append((rec.id, ""
                                "[%s] - %s" % (rec.sequence_number,rec.name)))
        return res


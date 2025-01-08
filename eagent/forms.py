from django import forms

class EmailCommandForm(forms.Form):
    input_command = forms.CharField(
        label="Input Command",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Enter your email command here..."}),
        required=True
    )

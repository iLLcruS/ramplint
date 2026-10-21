from django import forms
from django.utils.translation import gettext_lazy as _


class StarRatingWidget(forms.Widget):
    """Five radio buttons drawn as stars."""

    # The template drops widget.attrs, so the field's <label for> has nothing to point to.
    template_name = "widgets/star_rating.html"


class NewsletterForm(forms.Form):
    # An empty label with a placeholder: screen readers announce an input without a name.
    email = forms.EmailField(
        label="", widget=forms.EmailInput(attrs={"placeholder": _("Your email")})
    )


class ProfileForm(forms.Form):
    name = forms.CharField(label=_("Name"))
    city = forms.CharField(label=_("City"), required=False)
    rating = forms.IntegerField(label=_("How do you like Shoply?"), widget=StarRatingWidget)

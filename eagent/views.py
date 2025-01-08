from django.shortcuts import render
from .forms import EmailCommandForm
from eagent.service.utils import safe_run_email_agent, format_email_summary

def email_agent_view(request):
    """
    Handle user input, process it with the email agent, and display the result.
    """
    result = None
    clean_output = None
    if request.method == "POST":
        form = EmailCommandForm(request.POST)
        if form.is_valid():
            input_command = {"input": form.cleaned_data["input_command"]}
            try:
                # Call the email agent
                response = safe_run_email_agent(input_command)
                # Format the output
                clean_output = format_email_summary(response)
            except Exception as e:
                clean_output = f"Error: {str(e)}"
    else:
        form = EmailCommandForm()

    return render(request, "eagent/email_agent.html", {"form": form, "clean_output": clean_output})

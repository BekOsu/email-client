from django.http import JsonResponse
from django.shortcuts import render, redirect
from .forms import EmailCommandForm
from eagent.service.utils import safe_run_email_agent, format_email_summary
import logging

logger = logging.getLogger(__name__)

def email_agent_view(request):
    """
    Handle user input, process it with the email agent, and display the result.
    """
    clean_output = None  # Initialize clean_output to avoid reference issues

    if request.method == "POST":
        form = EmailCommandForm(request.POST)
        if form.is_valid():
            input_command = {"input": form.cleaned_data["input_command"]}
            try:
                logger.info(f"Processing input: {input_command}")
                response = safe_run_email_agent(input_command)
                clean_output = format_email_summary(response)

                # Handle AJAX requests
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    logger.info("AJAX request processed successfully.")
                    return JsonResponse({"clean_output": clean_output})

                # Redirect after successful POST to prevent resubmission on refresh
                request.session["clean_output"] = clean_output
                return redirect("email_agent")
            except Exception as e:
                error_message = f"Error: {str(e)}"
                logger.error(f"Error during email agent execution: {error_message}")
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse({"clean_output": error_message})
                clean_output = error_message
    else:
        form = EmailCommandForm()
        # Retrieve clean_output from the session after redirect
        clean_output = request.session.pop("clean_output", None)

    return render(request, "eagent/email_agent.html", {"form": form, "clean_output": clean_output})

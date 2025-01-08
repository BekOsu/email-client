from django.http import JsonResponse
from eagent.service.utils import get_agent_executor


def check_emails(request):
    try:
        agent_executor = get_agent_executor()
        input_command = {"input": "How many emails did I receive today?"}
        result = agent_executor.invoke(input_command)
        return JsonResponse({"result": result}, safe=False)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

// utils/responseUtils.cjs
const createResponse = (success, message, data = null) => {
  const response = {
    success,
    message,
    timestamp: new Date().toISOString()
  };
  if (data) {
    response.data = data;
  }
  return response;
};

const createErrorResponse = (message, statusCode = 500, details = null) => {
  const response = createResponse(false, message);
 
  if (details) {
    response.details = details;
  }
 
  return response;
};

module.exports = {
  createResponse,
  createErrorResponse
};
// lib/services/user_session.dart

class UserSession {
  static String organizationName = 'Nimbus Microfinance';
  static String branchName = 'Ndola Branch';
  static String officerName = 'Field Officer';
  
  // This maps the UUIDs from your backend to friendly names.
  // Add more as you discover them in your database.
  static String getFriendlyBranchName(String branchId) {
    if (branchId == 'ee52277c-c5b7-4d1d-807c-79c375551bdf') {
      return 'Ndola Branch';
    } else if (branchId == 'lusaka-uuid-1234') {
      return 'Lusaka Main Branch';
    }
    // If it's already a string like "Ndola Branch" (not a UUID), just return it
    if (!branchId.contains('-')) {
      return branchId;
    }
    return branchId; // Fallback to UUID if not found
  }
}
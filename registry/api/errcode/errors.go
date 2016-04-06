package errcode

type ErrorCode int

type ErrorDescriptor struct {
	Code    ErrorCode
	Message string
	Details string
}

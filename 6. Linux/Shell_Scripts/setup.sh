#!/bin/bash

# echo "Hello from bash script"

# filename=config.yaml

# if [ -d  "config" ]
# then
#     echo "Reading config file contents"
#     config_file=$(ls config)
# else
#     echo "config directory not found, creating one"
#     mkdir confi 
# fi

# echo "Here are all configuration files: $config_file"

# user_group=$1
# if [ "$user_group" == "devops" ]
# then 
#     echo "configure the server"
# elif [ "$user_group" == "admin" ]
# then
#     echo "administer the server"
# else    
#     echo "No permission to configure the server"
# fi

# echo "Reading user input"
# read -p "Enter username: " username
# read -p "Enter password: " password

# echo "Printing information"
# echo "Username: $username"
# echo "Password: $password"

# for param in $*
#      do
#       echo "$param"
#      done

# sum=0
# while true
#  do 
#   read -p "enter a score: " score

#   if [ "$score" == "q" ]
#   then 
#     break;
#   fi
    
#   sum=$(($sum + $score))      # for arithmetic operations
#   echo "Total score: $sum"
#  done

# function score_sum {  # or function (){} works fine
#     sum=0
#     while true
#     do 
#     read -p "enter a score: " score

#     if [ "$score" == "q" ]
#     then 
#         break;
#     fi
        
#     sum=$(($sum + $score))      # for arithmetic operations
#     echo "Total score: $sum"
#     done
# }
# score_sum

# function create_file(){
#     file_name=$1
#     touch $file_name
# }
# create_file names.txt
# create_file enrollment.txt
# create_file test.sh

function sum(){
    total=$(($1+$2))
    return $total
}
sum 4 5
result=$?
echo "$result" 